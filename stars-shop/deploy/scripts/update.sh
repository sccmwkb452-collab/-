#!/usr/bin/env bash
# Zero-surprise update: backup → pull → build → migrate → restart → health check.
source "$(dirname "$0")/lib.sh"
load_env
log "backup before update"
BACKUP_PREFIX=pre-update "$ROOT/deploy/scripts/backup.sh"
if git -C "$ROOT" rev-parse >/dev/null 2>&1; then
  log "pulling latest code"
  git -C "$ROOT" pull --ff-only
fi
log "building images"
"${COMPOSE[@]}" build
log "applying migrations"
"${COMPOSE[@]}" run --rm migrate
log "restarting services"
"${COMPOSE[@]}" up -d --remove-orphans
wait_healthy api || die "API did not become healthy — inspect: docker compose logs api"
"$ROOT/deploy/scripts/diagnose.sh" --short
docker image prune -f >/dev/null
log "update finished"
