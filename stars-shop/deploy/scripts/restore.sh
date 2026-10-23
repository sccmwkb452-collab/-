#!/usr/bin/env bash
# Restore a backup:  ./deploy/scripts/restore.sh backups/starshop-YYYYmmdd-HHMMSS.dump
# Stops the app processes, restores the database, runs migrations, starts again.
source "$(dirname "$0")/lib.sh"
load_env
FILE="${1:-}"
[ -f "$FILE" ] || die "usage: $0 <backup.dump>"
read -r -p "This REPLACES the current database with $FILE. Type 'restore' to continue: " answer
[ "$answer" = "restore" ] || die "aborted"
log "safety backup of the current state first"
BACKUP_PREFIX=pre-restore "$ROOT/deploy/scripts/backup.sh" || warn "safety backup failed (continuing)"
"${COMPOSE[@]}" stop api worker bot
"${COMPOSE[@]}" exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$FILE"
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d api worker bot
wait_healthy api && log "restore complete"
