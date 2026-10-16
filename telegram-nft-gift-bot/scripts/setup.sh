#!/bin/sh
# First-time setup on a fresh Ubuntu VPS. Run from the project folder:  sh scripts/setup.sh
set -e
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  chmod 600 .env
  # Fernet key = urlsafe base64 of 32 random bytes
  KEY=$(openssl rand -base64 32 | tr '+/' '-_')
  PASS=$(openssl rand -hex 24)
  sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$KEY|" .env
  sed -i "s|change-me-to-a-long-random-password|$PASS|g" .env
  echo "==> Generated ENCRYPTION_KEY and database password."
  echo "    Now edit .env and set BOT_TOKEN, ADMIN_IDS and TON_RECEIVER_ADDRESS:  nano .env"
  echo "    Then run:  sudo docker compose up -d --build"
  exit 0
fi

echo "==> Starting"
sudo docker compose up -d --build
sudo docker compose ps
