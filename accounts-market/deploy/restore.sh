#!/usr/bin/env bash
# Restore: ./deploy/restore.sh backups/market-....sql.gz
# Stops the bot, recreates the database from the dump, starts the bot again.
set -euo pipefail
cd "$(dirname "$0")/.."
dump="${1:?usage: deploy/restore.sh backups/market-YYYYmmdd-HHMMSS.sql.gz}"
[ -f "$dump" ] || { echo "no such file: $dump"; exit 1; }
read -r -p "The current database will be REPLACED by $dump. Type 'yes' to continue: " answer
[ "$answer" = "yes" ] || { echo "cancelled"; exit 1; }
./deploy/backup.sh   # safety copy of the current state
docker compose stop bot
docker compose exec -T db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
gunzip -c "$dump" | docker compose exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose start bot
echo "Restored from $dump"
