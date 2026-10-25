#!/usr/bin/env bash
# Manual backup: ./deploy/backup.sh  → backups/market-YYYYmmdd-HHMMSS.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
file="backups/market-$(date -u +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T db sh -c 'pg_dump --no-owner -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -9 > "$file"
echo "Saved $file ($(du -h "$file" | cut -f1))"
