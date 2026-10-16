#!/bin/sh
# Apply database migrations, then start the bot.
set -e
cd "$(dirname "$0")/.."
python -m alembic upgrade head
exec python -m nft_gift_bot
