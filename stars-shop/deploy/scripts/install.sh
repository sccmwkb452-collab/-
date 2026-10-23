#!/usr/bin/env bash
# First-time setup on a fresh Ubuntu 22.04/24.04 VPS (run as root or with sudo):
#   git clone <repo> /opt/starshop && cd /opt/starshop/stars-shop
#   sudo ./deploy/scripts/install.sh
source "$(dirname "$0")/lib.sh"

[ "$(id -u)" -eq 0 ] || die "run with sudo"

if ! command -v docker >/dev/null 2>&1; then
  log "installing Docker Engine"
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg cron
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

if [ ! -f /etc/docker/daemon.json ]; then
  log "configuring Docker log rotation"
  cat > /etc/docker/daemon.json <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
JSON
  systemctl restart docker
fi

if [ ! -f "$ROOT/.env" ]; then
  log "creating .env from .env.example with random secrets"
  cp "$ROOT/.env.example" "$ROOT/.env"
  sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" "$ROOT/.env"
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" "$ROOT/.env"
  sed -i "s/^BOT_WEBHOOK_SECRET=.*/BOT_WEBHOOK_SECRET=$(openssl rand -hex 24)/" "$ROOT/.env"
  chmod 600 "$ROOT/.env"
  warn "Fill in DOMAIN, LETSENCRYPT_EMAIL, BOT_TOKEN, BOT_USERNAME and ADMIN_TELEGRAM_IDS in $ROOT/.env, then run this script again."
  exit 0
fi
load_env
[ -n "${DOMAIN:-}" ] && [ "$DOMAIN" != "shop.example.com" ] || die "set DOMAIN in .env"
[ -n "${BOT_TOKEN:-}" ] || die "set BOT_TOKEN in .env"
[ -n "${ADMIN_TELEGRAM_IDS:-}" ] || warn "ADMIN_TELEGRAM_IDS is empty — nobody will be able to open the admin panel"

if command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp >/dev/null || true
  ufw allow 80/tcp >/dev/null || true
  ufw allow 443/tcp >/dev/null || true
fi

log "building and starting the stack"
"${COMPOSE[@]}" up -d --build

log "requesting a Let's Encrypt certificate for $DOMAIN"
"$ROOT/deploy/scripts/init-letsencrypt.sh"

log "installing daily database backup (03:17) into crontab"
CRON_LINE="17 3 * * * $ROOT/deploy/scripts/backup.sh >> /var/log/starshop-backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'starshop.*backup.sh' ; echo "$CRON_LINE" ) | crontab -

log "done. Check: $ROOT/deploy/scripts/diagnose.sh"
log "Mini App URL for @BotFather (/newapp or Bot Settings → Menu Button): https://$DOMAIN/"
