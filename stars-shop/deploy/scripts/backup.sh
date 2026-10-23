#!/usr/bin/env bash
# PostgreSQL backup in custom format, kept for BACKUP_KEEP_DAYS (default 14).
# Optional off-site copy: set BACKUP_RCLONE_REMOTE (e.g. "s3:bucket/starshop") and install rclone.
source "$(dirname "$0")/lib.sh"
load_env
DIR="${BACKUP_DIR:-$ROOT/backups}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$DIR"
chmod 700 "$DIR"
# BACKUP_PREFIX distinguishes automatic safety copies (pre-update, pre-restore).
FILE="$DIR/starshop-${BACKUP_PREFIX:+$BACKUP_PREFIX-}$(date -u +%Y%m%d-%H%M%S)-$$.dump"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
chmod 600 "$FILE"
[ -s "$FILE" ] || die "backup is empty: $FILE"
log "backup written: $FILE ($(du -h "$FILE" | cut -f1))"
find "$DIR" -name 'starshop-*.dump' -mtime +"$KEEP" -delete
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
  rclone copy "$FILE" "$BACKUP_RCLONE_REMOTE" && log "copied to $BACKUP_RCLONE_REMOTE"
fi
