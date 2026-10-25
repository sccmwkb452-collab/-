#!/bin/sh
# Runs inside the `backup` container: pg_dump every BACKUP_INTERVAL_HOURS, keeps BACKUP_KEEP_DAYS.
set -eu
while true; do
  file="/backups/market-$(date -u +%Y%m%d-%H%M%S).sql.gz"
  if pg_dump --no-owner --format=plain | gzip -9 > "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup saved: $file"
  else
    rm -f "$file.tmp"
    echo "backup FAILED" >&2
  fi
  find /backups -name 'market-*.sql.gz' -mtime +"$BACKUP_KEEP_DAYS" -delete
  sleep $(( BACKUP_INTERVAL_HOURS * 3600 ))
done
