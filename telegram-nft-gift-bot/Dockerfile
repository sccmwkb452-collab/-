FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini pyproject.toml ./
COPY alembic ./alembic
COPY nft_gift_bot ./nft_gift_bot
COPY scripts ./scripts

# Never run as root
RUN useradd --create-home --uid 10001 bot && chown -R bot /app
USER bot

CMD ["sh", "scripts/run_bot.sh"]
