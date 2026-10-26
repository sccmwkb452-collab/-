#!/usr/bin/env bash
# Restore a backup made by backup.sh. This REPLACES the current database, so the
# script first makes a fresh backup of the current state and asks for --yes.
#
#   deploy/scripts/restore.sh backups/pac-20261026-042000.dump [backups/storage-20261026-042000.tar.gz] --yes
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=${COMPOSE:-docker compose}

dump=""
storage=""
confirmed=0
for arg in "$@"; do
  case "$arg" in
    --yes) confirmed=1 ;;
    *.dump) dump=$arg ;;
    *.tar.gz) storage=$arg ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ -z "$dump" || ! -f "$dump" ]]; then
  echo "usage: $0 <pac-*.dump> [storage-*.tar.gz] --yes" >&2
  exit 2
fi
if [[ $confirmed -ne 1 ]]; then
  echo "Restoring replaces the current database with $dump." >&2
  echo "Re-run with --yes to continue (a backup of the current state is made first)." >&2
  exit 1
fi

$COMPOSE exec -T db pg_restore --list < "$dump" > /dev/null

echo "== backup of the current state"
"$(dirname "$0")/backup.sh"

echo "== stopping api, worker and bot"
$COMPOSE stop api worker bot

echo "== restoring database"
$COMPOSE exec -T db pg_restore -U pac -d pac --clean --if-exists --no-owner --single-transaction < "$dump"

if [[ -n "$storage" ]]; then
  echo "== restoring storage"
  $COMPOSE run --rm --no-deps -T api tar -C /app/storage -xzf - < "$storage"
fi

echo "== starting services"
$COMPOSE up -d
echo "restore ok"
