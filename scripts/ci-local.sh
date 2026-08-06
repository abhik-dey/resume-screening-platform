#!/usr/bin/env bash
# Run the CI checks locally.
#
# CI you can only trigger by pushing is a slow feedback loop, and the four
# bugs this pipeline was built around were all things a local run would
# have caught if the check had existed.
#
#   ./scripts/ci-local.sh          all checks
#   ./scripts/ci-local.sh fast     skip the Docker checks
set -uo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-all}"
PASS=0; FAIL=0; SKIP=0

step() { printf "\n\033[1m-- %s\033[0m\n" "$1"; }
ok()   { printf "  \033[32mPASS\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
skip() { printf "  \033[33mSKIP\033[0m %s (%s)\n" "$1" "$2"; SKIP=$((SKIP+1)); }

run() {  # run <name> <command...>
  local name="$1"; shift
  if "$@" > /tmp/ci-step.log 2>&1; then
    ok "$name"
  else
    bad "$name"
    sed 's/^/       /' /tmp/ci-step.log | tail -15
  fi
}

step "Backend lint"
if command -v ruff > /dev/null 2>&1; then
  (cd backend && run "ruff" ruff check app tests)
else
  skip "ruff" "pip install ruff"
fi

step "GitHub Actions workflows"
if command -v actionlint > /dev/null 2>&1; then
  # Validates GitHub's expression language, which a YAML schema check cannot:
  # an expression lives inside a string, so a quoting error is structurally
  # valid YAML and a workflow-level parse failure.
  run "actionlint" actionlint .github/workflows/ci.yml .github/workflows/cd.yml
else
  skip "actionlint" "https://github.com/rhysd/actionlint/releases"
fi

step "Kubernetes manifests"
if python3 -c "import kubernetes_validate" 2>/dev/null; then
  run "schema + security assertions" python3 k8s/validate.py
else
  skip "k8s validate" "pip install kubernetes-validate"
fi

step "Frontend"
if [ -d frontend/node_modules ]; then
  (cd frontend && run "typescript" npx tsc --noEmit)
  (cd frontend && run "production build" npm run build)
else
  skip "frontend" "run 'npm ci' in frontend/"
fi

step "Backend tests"
if command -v pytest > /dev/null 2>&1; then
  # Mirrors CI: local providers so no real API is ever called.
  (cd backend && EMBEDDING_PROVIDER=local VECTOR_STORE_BACKEND=memory \
     POSTGRES_HOST=localhost REDIS_HOST=localhost \
     run "pytest" pytest -q)
else
  skip "pytest" "not on PATH — activate your virtualenv"
fi

step "Secret scan"
if grep -rEn "(sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{30,})" \
     --include="*.py" --include="*.ts" --include="*.tsx" \
     --include="*.yml" --include="*.yaml" --include="*.sh" . > /dev/null 2>&1; then
  bad "no committed credentials"
  grep -rEn "(sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{30,})" \
    --include="*.py" --include="*.ts" --include="*.tsx" \
    --include="*.yml" --include="*.yaml" --include="*.sh" . 2>/dev/null | sed 's/^/       /'
else
  ok "no committed credentials"
fi

if git ls-files --error-unmatch k8s/secret.generated.yaml > /dev/null 2>&1; then
  bad "generated secret must not be tracked by git"
else
  ok "generated secret not tracked by git"
fi

if git ls-files --error-unmatch backend/.env.prod > /dev/null 2>&1; then
  bad "backend/.env.prod must not be tracked by git"
else
  ok "backend/.env.prod not tracked by git"
fi

step "Docker"
if [ "$MODE" = "fast" ]; then
  skip "docker checks" "fast mode"
elif command -v docker > /dev/null 2>&1 && docker info > /dev/null 2>&1; then
  # The dev stack needs backend/.env, which is gitignored. Create one from
  # the template if it's absent, so this checks the compose file rather than
  # just reporting a missing file.
  if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo "       (created backend/.env from the template)"
  fi
  run "dev compose parses" docker compose -f infra/docker-compose.yml config -q

  # The Phase 21 check: Compose resolves ${VAR} from a .env beside the
  # compose file, NOT from a service's env_file.
  if [ -f backend/.env.prod ]; then
    ln -sf ../backend/.env.prod infra/.env
    run "prod compose resolves" docker compose -f infra/docker-compose.prod.yml config -q
  else
    skip "prod compose" "no backend/.env.prod"
  fi
else
  skip "docker checks" "docker unavailable"
fi

printf "\n\033[1m%d passed, %d failed, %d skipped\033[0m\n" "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]
