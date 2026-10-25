#!/usr/bin/env bash
# Ubuntu 22.04/24.04 VPS setup: installs Docker, prepares .env, starts the stack.
# Run from the project folder: sudo ./deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  apt-get update -y
  apt-get install -y ca-certificates curl
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null

if [ ! -f .env ]; then
  cp .env.example .env
  password=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${password}/" .env
  chmod 600 .env
  echo "==> .env created. Fill in BOT_TOKEN, ADMIN_IDS and the payment provider, then run this script again."
  exit 0
fi

grep -q '^BOT_TOKEN=.\+' .env || { echo "BOT_TOKEN is empty in .env"; exit 1; }
mkdir -p backups
chmod +x deploy/*.sh

echo "==> Building and starting"
docker compose up -d --build
if grep -q '^DOMAIN=.\+' .env; then
  docker compose --profile webhook up -d caddy
fi
sleep 5
docker compose ps
echo "==> Done. Logs: docker compose logs -f bot"
