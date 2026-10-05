#!/bin/bash
# Установка/обновление бота на Ubuntu-сервере одной командой:
#   curl -fsSL https://raw.githubusercontent.com/sccmwkb452-collab/-/telegram-bot/telegram-bot/deploy.sh | bash
set -euo pipefail

BOT_DIR="${BOT_DIR:-/root/telegram-bot}"
REPO="https://github.com/sccmwkb452-collab/-.git"
BRANCH="telegram-bot"
SRC="$BOT_DIR/.src"

echo "== 1/4 Системные пакеты"
if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq git python3 python3-venv python3-pip >/dev/null
fi

echo "== 2/4 Код бота"
if [ -d "$SRC/.git" ]; then
    git -C "$SRC" fetch -q origin "$BRANCH"
    git -C "$SRC" reset -q --hard "origin/$BRANCH"
else
    rm -rf "$SRC"
    git clone -q --depth 1 -b "$BRANCH" "$REPO" "$SRC"
fi
mkdir -p "$BOT_DIR/data/sessions"
cp -r "$SRC/telegram-bot/." "$BOT_DIR/"
cd "$BOT_DIR"

echo "== 3/4 Python-зависимости (venv)"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q --upgrade pip setuptools wheel
venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
    echo
    echo "!! Нет файла $BOT_DIR/.env — создайте его (BOT_TOKEN, API_ID, API_HASH, ALERT_CHAT_ID, ADMIN_IDS)"
    echo "   и запустите этот скрипт ещё раз."
    exit 1
fi

echo "== 4/4 Запуск как systemd-сервис"
if [ "${SKIP_SYSTEMD:-0}" = 1 ] || ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd пропущен. Ручной запуск: cd $BOT_DIR && venv/bin/python main.py"
    exit 0
fi

cat > /etc/systemd/system/telegram-bot.service <<EOF
[Unit]
Description=Telegram Market Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable -q telegram-bot
systemctl restart telegram-bot
sleep 6
systemctl --no-pager --lines=15 status telegram-bot || true

echo
echo "Готово. Логи:        journalctl -u telegram-bot -f"
echo "        Перезапуск:  systemctl restart telegram-bot"
echo "        Сессии:      положите *.session в $BOT_DIR/data/sessions/ или загрузите через админ-меню бота"
