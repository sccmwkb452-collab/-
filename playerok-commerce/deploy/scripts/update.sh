#!/usr/bin/env bash
# Update to the latest code of the current branch: backup, rebuild, migrate
# (the "migrate" service runs before the API starts), restart, wait for health.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=${COMPOSE:-docker compose}

git pull --ff-only
"$(dirname "$0")/backup.sh"
$COMPOSE up -d --build --remove-orphans

echo "== waiting for the services to become healthy"
for _ in $(seq 1 40); do
  states=$($COMPOSE ps --format '{{.Service}}={{.Health}}' api worker bot)
  if ! grep -qv '=healthy' <<<"$states"; then
    echo "$states"
    echo "update ok"
    exit 0
  fi
  sleep 6
done
echo "services are not healthy after 4 minutes:" >&2
$COMPOSE ps >&2
$COMPOSE logs --tail 50 api worker bot >&2
exit 1
