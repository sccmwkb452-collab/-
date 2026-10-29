#!/usr/bin/env bash
# Запуск в контейнере хостинга (H1Panel/Pterodactyl): команда запуска — `bash start.sh`.
# Токен берётся из переменной BOT_TOKEN или из файла .env рядом (BOT_TOKEN=...).
# Сам ставит зависимости и перезапускает бота, если он упал.
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
PY=$(command -v python3 || command -v python)
[ -d .venv ] || "$PY" -m venv .venv 2>/dev/null || true
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
"$PY" -m pip install -q --disable-pip-version-check -r requirements.txt \
  || "$PY" -m pip install -q --user --disable-pip-version-check -r requirements.txt
while true; do
  "$PY" bot.py
  echo "Бот остановился (код $?), перезапуск через 5 секунд…"
  sleep 5
done
