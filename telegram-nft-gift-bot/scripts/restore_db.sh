#!/bin/sh
# Restore a dump made by backup_db.sh:  sh scripts/restore_db.sh backups/nft_bot_YYYYmmdd_HHMMSS.sql.gz
set -e
cd "$(dirname "$0")/.."
. ./.env
[ -f "$1" ] || { echo "Usage: $0 <backup.sql.gz>"; exit 1; }
docker compose stop bot
gunzip -c "$1" | docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
docker compose start bot
