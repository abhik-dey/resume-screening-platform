#!/usr/bin/env python3
"""
Validate the Kubernetes manifests.

Two layers:
  1. Schema validation against real Kubernetes OpenAPI definitions
  2. Assertions on the security and correctness properties these manifests
     are supposed to have — schema validity says a manifest parses, not
     that it does what it claims

Run: python3 k8s/validate.py
"""
import glob
import sys

import yaml

try:
    import kubernetes_validate
except ImportError:
    print("pip install kubernetes-validate")
    sys.exit(2)

K8S_VERSION = "1.29.0"
# Config keys that pattern-match credential names but aren't secrets.
NON_SECRET_ALLOWLIST = {"ACCESS_TOKEN_EXPIRE_MINUTES", "GITHUB_TOOL_ENABLED"}


def load():
    docs = []
    for path in sorted(glob.glob("k8s/base/*.yaml")):
        if "template" in path:
            continue
        docs += [d for d in yaml.safe_load_all(open(path)) if d]
    return docs


def main() -> int:
    docs = load()
    by_kind: dict[str, list] = {}
    for d in docs:
        by_kind.setdefault(d["kind"], []).append(d)

    print(f"=== SCHEMA VALIDATION (Kubernetes {K8S_VERSION}, strict) ===")
    failed = 0
    for d in docs:
        try:
            kubernetes_validate.validate(d, K8S_VERSION, strict=True)
        except Exception as exc:
            failed += 1
            print(f"  FAIL {d['kind']}/{d['metadata']['name']}: {exc}")
    print(f"  {len(docs) - failed}/{len(docs)} resources valid\n")

    def workloads():
        out = []
        for kind in ("Deployment", "StatefulSet", "Job"):
            for d in by_kind.get(kind, []):
                out.append((f"{kind}/{d['metadata']['name']}", d["spec"]["template"]["spec"]))
        return out

    results = []

    def check(name, passed, detail=""):
        results.append((name, passed, detail))

    missing = [n for n, s in workloads()
               if s.get("securityContext", {}).get("runAsNonRoot") is not True]
    check("all workloads run as non-root", not missing, f"missing: {missing}")

    no_esc = [f"{n}:{c['name']}" for n, s in workloads() for c in s.get("containers", [])
              if c.get("securityContext", {}).get("allowPrivilegeEscalation") is not False]
    check("containers disallow privilege escalation (postgres/redis excepted)",
          all(x.startswith(("StatefulSet/postgres", "Deployment/redis")) for x in no_esc),
          f"unexpected: {no_esc}")

    no_limits = [f"{n}:{c['name']}" for n, s in workloads() for c in s.get("containers", [])
                 if not c.get("resources", {}).get("limits")
                 or not c.get("resources", {}).get("requests")]
    check("every container has requests and limits", not no_limits, f"missing: {no_limits}")

    backend = next(d for d in by_kind["Deployment"] if d["metadata"]["name"] == "backend")
    bc = backend["spec"]["template"]["spec"]["containers"][0]
    bspec = backend["spec"]["template"]["spec"]
    check("backend has startup, readiness and liveness probes",
          all(k in bc for k in ("startupProbe", "readinessProbe", "livenessProbe")))
    check("liveness more tolerant than readiness (no restart on transient slowness)",
          bc["livenessProbe"]["failureThreshold"] > bc["readinessProbe"]["failureThreshold"])
    check("grace period suits long LLM requests",
          bspec.get("terminationGracePeriodSeconds", 30) >= 60)
    check("preStop hook drains connections", "preStop" in bc.get("lifecycle", {}))

    for name in ("backend", "frontend"):
        d = next(x for x in by_kind["Deployment"] if x["metadata"]["name"] == name)
        check(f"{name} rollout never reduces capacity",
              d["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] == 0)

    pdb = by_kind["PodDisruptionBudget"][0]
    check("PDB allows node drain", pdb["spec"]["minAvailable"] < backend["spec"]["replicas"])

    ing = by_kind["Ingress"][0]
    snippet = ing["metadata"]["annotations"].get(
        "nginx.ingress.kubernetes.io/configuration-snippet", "")
    check("Ingress blocks /metrics (Phase 18)", "/metrics" in snippet and "deny all" in snippet)
    check("Ingress blocks API docs", "docs" in snippet)

    nps = by_kind["NetworkPolicy"]
    check("default-deny ingress exists",
          any(p["metadata"]["name"] == "default-deny-ingress" for p in nps))
    be_np = next(p for p in nps if p["metadata"]["name"] == "backend-ingress")
    check("backend reachable only from ingress + monitoring namespaces",
          len(be_np["spec"]["ingress"]) == 2)
    ds_np = next(p for p in nps if p["metadata"]["name"] == "datastore-ingress")
    check("datastores reachable only from backend pods",
          ds_np["spec"]["ingress"][0]["from"][0]["podSelector"]["matchLabels"]["app"] == "backend")

    check("no Secret in committed manifests", "Secret" not in by_kind)
    check("generated secret gitignored", "secret.generated.yaml" in open(".gitignore").read())

    cm = by_kind["ConfigMap"][0]["data"]
    leaked = [k for k in cm
              if k not in NON_SECRET_ALLOWLIST
              and any(t in k.upper() for t in ("PASSWORD", "SECRET", "API_KEY", "_TOKEN"))]
    check("no credentials in ConfigMap", not leaked, f"leaked: {leaked}")

    hpa = by_kind["HorizontalPodAutoscaler"][0]["spec"]
    check("HPA min replicas >= PDB minAvailable",
          hpa["minReplicas"] >= pdb["spec"]["minAvailable"])
    check("HPA scales down slower than up (bursty workload)",
          hpa["behavior"]["scaleDown"]["stabilizationWindowSeconds"]
          > hpa["behavior"]["scaleUp"]["stabilizationWindowSeconds"])

    job = by_kind["Job"][0]
    check("migration Job bounded retries", job["spec"]["backoffLimit"] <= 5)
    check("migration is a Job, not an initContainer", "initContainers" not in bspec)

    # Compose derives image tags from the project name unless `image:` is
    # pinned, which silently produced names the manifests didn't reference.
    # Asserted here so the two deployment paths can't drift apart again.
    compose = yaml.safe_load(open("infra/docker-compose.prod.yml"))
    built = {compose["services"][s].get("image") for s in ("backend", "frontend")}
    referenced = {c["image"] for _, s in workloads() for c in s.get("containers", [])
                  if "resume-screening" in c.get("image", "")}
    check("k8s image references match what compose builds",
          referenced.issubset(built), f"built={sorted(built)} referenced={sorted(referenced)}")

    print("=== BEHAVIORAL ASSERTIONS ===")
    bad = 0
    for name, passed, detail in results:
        print(f"  {'OK  ' if passed else 'FAIL'} {name}"
              + (f"  [{detail}]" if detail and not passed else ""))
        if not passed:
            bad += 1
    print(f"\n{len(results) - bad}/{len(results)} assertions passed")
    return 1 if (failed or bad) else 0


if __name__ == "__main__":
    sys.exit(main())
