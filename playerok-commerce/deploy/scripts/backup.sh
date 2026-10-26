#!/usr/bin/env bash
# Backup of the database and of the storage volume (generated images).
# Run from cron, e.g. daily at 04:20:
#   20 4 * * * /opt/playerok-commerce/deploy/scripts/backup.sh >> /var/log/pac-backup.log 2>&1
#
# BACKUP_DIR   where to put the files (default ./backups next to docker-compose.yml)
# KEEP_DAYS    backups older than this are removed (default 14)
# COMPOSE      compose command (default "docker compose")
set -euo pipefail

cd "$(dirname "$0")/../.."
BACKUP_DIR=${BACKUP_DIR:-./backups}
KEEP_DAYS=${KEEP_DAYS:-14}
COMPOSE=${COMPOSE:-docker compose}
stamp=$(date -u +%Y%m%d-%H%M%S)

umask 077
mkdir -p "$BACKUP_DIR"

dump="$BACKUP_DIR/pac-$stamp.dump"
$COMPOSE exec -T db pg_dump -U pac -d pac --format=custom > "$dump.part"
# a dump that pg_restore cannot list is not a backup
$COMPOSE exec -T db pg_restore --list < "$dump.part" > /dev/null
mv "$dump.part" "$dump"

storage="$BACKUP_DIR/storage-$stamp.tar.gz"
$COMPOSE run --rm --no-deps -T api tar -C /app/storage -czf - . > "$storage.part"
mv "$storage.part" "$storage"

find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'pac-*.dump' -o -name 'storage-*.tar.gz' \) -mtime "+$KEEP_DAYS" -delete

echo "backup ok: $dump ($(du -h "$dump" | cut -f1)), $storage ($(du -h "$storage" | cut -f1))"
