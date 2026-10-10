#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077

fail() { printf 'deploy: %s\n' "$1" >&2; exit 1; }
[[ $# -eq 2 ]] || fail "expected frontend and backend image references"

FRONTEND_IMAGE="$1"
BACKEND_IMAGE="$2"
CONFIG_FILE="${RCA_CONFIG_FILE:-/etc/rca-demo/config.env}"
[[ -r "$CONFIG_FILE" ]] || fail "instance configuration is unavailable"
# shellcheck disable=SC1090
set -a
source "$CONFIG_FILE"
set +a

valid_image() {
  local image="$1" repository="$2"
  [[ "$image" =~ ^[a-z0-9]+([._-][a-z0-9]+)*/[a-z0-9]+([._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$ ]] &&
    [[ "${image%@*}" == "$repository" ]]
}
valid_image "$FRONTEND_IMAGE" "${DOCKERHUB_FRONTEND_REPOSITORY:?}" || fail "frontend image is not an approved immutable reference"
valid_image "$BACKEND_IMAGE" "${DOCKERHUB_BACKEND_REPOSITORY:?}" || fail "backend image is not an approved immutable reference"

CONFIG_DIR="${RCA_CONFIG_DIR:-/etc/rca-demo}"
COMPOSE_FILE="${RCA_COMPOSE_FILE:-$CONFIG_DIR/compose.prod.yaml}"
[[ -r "$COMPOSE_FILE" ]] || fail "production Compose file is unavailable"

docker pull "$FRONTEND_IMAGE" || fail "could not pull approved frontend image"
docker pull "$BACKEND_IMAGE" || fail "could not pull approved backend image"

export FRONTEND_IMAGE BACKEND_IMAGE

compose() {
  docker compose --env-file "$CONFIG_FILE" -f "$COMPOSE_FILE" "$@"
}

compose up -d --wait --wait-timeout 240 || fail "Docker Compose failed to start healthy services"
for attempt in $(seq 1 30); do
  if curl --fail --silent --max-time 10 \
    --resolve "$RCA_DEMO_HOST:443:127.0.0.1" "https://$RCA_DEMO_HOST/api/demo/health" >/dev/null; then
    echo "deploy: frontend and backend are healthy"
    exit 0
  fi
  sleep 2
done
fail "HTTPS application health check failed"
