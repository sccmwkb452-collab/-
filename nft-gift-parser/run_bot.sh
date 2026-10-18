#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
if [ -z "$BOT_TOKEN" ]; then read -rp "Вставьте токен бота и нажмите Enter: " BOT_TOKEN; export BOT_TOKEN; fi
python bot.py
