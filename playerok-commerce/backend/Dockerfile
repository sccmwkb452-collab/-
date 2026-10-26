# One image for the API, the worker, the bot and the migration job;
# the docker-compose service chooses the command.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    STORAGE_DIR=/app/storage

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/storage \
    && chown app:app /app/storage

COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app assets ./assets
COPY --chown=app:app autocommerce ./autocommerce

USER app
EXPOSE 8000

# X-Forwarded-For is evaluated by the app itself (TRUSTED_PROXY_HOPS), so uvicorn
# must not rewrite the client address from untrusted headers.
CMD ["uvicorn", "autocommerce.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-proxy-headers"]
