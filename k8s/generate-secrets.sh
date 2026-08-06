#!/usr/bin/env bash
# Generate the Kubernetes Secret from the template.
#
# Writes to k8s/secret.generated.yaml, which is gitignored. A manifest
# containing a real JWT signing key is in the repository history forever,
# and rotating the key afterwards doesn't remove it from history.
#
# For production, prefer External Secrets Operator or Sealed Secrets:
# Kubernetes Secrets are base64-encoded, not encrypted, and anyone with
# read access to the namespace can decode them.
set -euo pipefail

cd "$(dirname "$0")/.."
OUTPUT="k8s/secret.generated.yaml"

if [ -f "$OUTPUT" ]; then
  echo "$OUTPUT already exists. Delete it first to regenerate."
  echo "WARNING: regenerating JWT_SECRET_KEY invalidates every issued token."
  exit 1
fi

# Reuse the production env file if present, so the cluster and the compose
# deployment don't drift apart.
if [ -f backend/.env.prod ]; then
  echo "Reading values from backend/.env.prod"
  get() { grep "^$1=" backend/.env.prod | cut -d'=' -f2- || true; }
  POSTGRES_USER="$(get POSTGRES_USER)"
  POSTGRES_PASSWORD="$(get POSTGRES_PASSWORD)"
  JWT_SECRET_KEY="$(get JWT_SECRET_KEY)"
  OPENAI_API_KEY="$(get OPENAI_API_KEY)"
  ANTHROPIC_API_KEY="$(get ANTHROPIC_API_KEY)"
  GITHUB_TOKEN="$(get GITHUB_TOKEN)"
else
  echo "No backend/.env.prod found — generating fresh credentials."
  POSTGRES_USER="resume_user"
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
  JWT_SECRET_KEY="$(openssl rand -hex 32)"
  OPENAI_API_KEY="${OPENAI_API_KEY:-}"
  ANTHROPIC_API_KEY=""
  GITHUB_TOKEN=""
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "WARNING: OPENAI_API_KEY is empty. Agents will fail until it is set."
fi

cat > "$OUTPUT" <<YAML
# GENERATED FILE — DO NOT COMMIT. Regenerate with k8s/generate-secrets.sh
apiVersion: v1
kind: Secret
metadata:
  name: backend-secrets
  namespace: resume-screening
type: Opaque
stringData:
  POSTGRES_USER: "${POSTGRES_USER}"
  POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
  JWT_SECRET_KEY: "${JWT_SECRET_KEY}"
  OPENAI_API_KEY: "${OPENAI_API_KEY}"
  ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
  GITHUB_TOKEN: "${GITHUB_TOKEN}"
YAML

chmod 600 "$OUTPUT"
echo "Wrote $OUTPUT (gitignored, mode 600)"
echo "Apply with: kubectl apply -f $OUTPUT"
