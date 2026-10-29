#!/usr/bin/env bash
# Установка бота на сервер Ubuntu/Debian как системного сервиса (работает 24/7,
# сам перезапускается при падении и после перезагрузки сервера).
#
# Запуск из папки nft-gift-parser на сервере:
#   sudo BOT_TOKEN=123:ABC bash deploy/install.sh
# Повторный запуск обновляет код и перезапускает бота, база сохраняется.
set -euo pipefail

APP_DIR=/opt/nft-gift-bot
SERVICE=nft-gift-bot
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "Запусти через sudo"; exit 1; }

apt-get update -qq
apt-get install -y -qq python3 python3-venv rsync >/dev/null

id -u nftbot >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin nftbot
mkdir -p "$APP_DIR/data"
rsync -a --delete --exclude data --exclude .venv --exclude '__pycache__' --exclude '*.db*' \
  "$SRC_DIR/" "$APP_DIR/app/"

[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/app/requirements.txt"

ENV_FILE=/etc/$SERVICE.env
if [ -n "${BOT_TOKEN:-}" ] || [ ! -f "$ENV_FILE" ]; then
  [ -n "${BOT_TOKEN:-}" ] || read -rp "Токен бота: " BOT_TOKEN
  umask 077
  cat > "$ENV_FILE" <<ENV
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=${ADMIN_IDS:-8790784360}
DB_PATH=$APP_DIR/data/gifts.db
ENV
fi

cat > /etc/systemd/system/$SERVICE.service <<UNIT
[Unit]
Description=NFT gift parser Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
User=nftbot
WorkingDirectory=$APP_DIR/app
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

chown -R nftbot:nftbot "$APP_DIR"
systemctl daemon-reload
systemctl enable --now $SERVICE
systemctl restart $SERVICE
sleep 3
systemctl --no-pager --lines=5 status $SERVICE || true
echo
echo "Готово. Логи: journalctl -u $SERVICE -f"
