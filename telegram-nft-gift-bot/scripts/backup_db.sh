#!/bin/sh
# Dump PostgreSQL from the docker-compose "db" service into ./backups and keep the last 14 dumps.
# Cron example (daily 03:17):  17 3 * * * cd /opt/nft-gift-bot && sh scripts/backup_db.sh
set -e
cd "$(dirname "$0")/.."
. ./.env
mkdir -p backups
umask 077
FILE="backups/nft_bot_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$FILE"
ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm --
echo "Backup saved: $FILE"
