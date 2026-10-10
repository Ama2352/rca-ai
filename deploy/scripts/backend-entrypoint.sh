#!/usr/bin/env bash
set -euo pipefail
set +x

SECRET_DIR="${RCA_SECRET_DIR:-/run/secrets}"
GROQ_API_KEY="$(cat "$SECRET_DIR/groq_api_key")"
CEREBRAS_API_KEY="$(cat "$SECRET_DIR/cerebras_api_key")"
if [[ -z "$GROQ_API_KEY" || -z "$CEREBRAS_API_KEY" ]]; then
  echo "backend-entrypoint: required provider credential file is empty" >&2
  exit 40
fi
export GROQ_API_KEY CEREBRAS_API_KEY
exec "$@"
