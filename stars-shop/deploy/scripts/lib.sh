#!/usr/bin/env bash
# Shared helpers for deploy scripts. Run scripts from anywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f "$ROOT/docker-compose.yml")

log() { printf '\033[1;34m[starshop]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

load_env() {
  [ -f "$ROOT/.env" ] || die ".env not found — copy .env.example to .env first"
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
}

# Wait until a compose service reports healthy (default 90 s).
wait_healthy() {
  local service="$1" timeout="${2:-90}" waited=0 cid status
  cid="$("${COMPOSE[@]}" ps -q "$service")"
  [ -n "$cid" ] || die "service $service is not running"
  while [ "$waited" -lt "$timeout" ]; do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
    [ "$status" = "healthy" ] && return 0
    sleep 2
    waited=$((waited + 2))
  done
  warn "$service is not healthy after ${timeout}s (status: $status)"
  return 1
}
