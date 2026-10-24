"""Serverless hosting (Vercel): ``api/index.py`` serves ``create_app()``.

Such a host has no worker process, no release step and no long-lived
connections, so this module
* fills in DEMO defaults for the environment variables that are not set;
* prepares the database on the first request of each instance: migrations
  under an advisory lock, the demo catalog for a new database, the admins;
* runs the background jobs after requests (``worker.inline``);
* receives Telegram updates over a webhook when BOT_TOKEN is set.

See docs/VERCEL.md.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
import time
from collections.abc import MutableMapping
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Receive, Scope, Send

from .api.ratelimit import get_limiter
from .cli import seed_catalog
from .config import Settings, get_settings
from .database.session import dispose_engine, get_engine
from .logging_setup import setup_logging
from .services.admin_auth import ensure_bootstrap_admins
from .worker import inline

log = logging.getLogger("starshop.serverless")
BACKEND = Path(__file__).resolve().parents[1]
MIGRATION_LOCK = 0x53544152  # pg_advisory_xact_lock key shared by all instances

DEFAULTS = {
    "APP_ENV": "production",
    "APP_MODE": "demo",
    "PAYMENT_PROVIDERS": "demo",
    "DELIVERY_PROVIDER": "demo",
    "PUBLIC_DEMO": "true",
    "INLINE_WORKER": "true",
    "AUTO_MIGRATE": "true",
    "DATABASE_POOL_SIZE": "0",
    "BOT_MODE": "webhook",
}
# Set by the Postgres integrations of Vercel (Neon, Supabase). A direct
# connection goes first: the migration lock needs a real session.
DATABASE_URL_VARS = ("DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING", "DATABASE_URL", "POSTGRES_URL")
UNAVAILABLE = {"error": {"code": "database_unavailable", "message": "База данных недоступна. Попробуйте через минуту"}}

_ready = False
_lock: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None
_webhook_due_at = 0.0  # monotonic time of the next webhook check


def configure_environment(env: MutableMapping[str, str]) -> None:
    """Defaults for a DEMO deployment; whatever is set explicitly wins."""
    for key, value in DEFAULTS.items():
        env.setdefault(key, value)
    url = next((env[key] for key in DATABASE_URL_VARS if env.get(key)), None)
    if url:
        env["DATABASE_URL"] = url
    host = env.get("VERCEL_PROJECT_PRODUCTION_URL") or env.get("VERCEL_URL")
    if host and not env.get("PUBLIC_BASE_URL"):
        env["PUBLIC_BASE_URL"] = f"https://{host}"
    if url and not env.get("SECRET_KEY"):
        # As secret as the database password and stable while it does not change.
        env["SECRET_KEY"] = hashlib.sha256(f"starshop-secret:{url}".encode()).hexdigest()


def bot_webhook_enabled(settings: Settings) -> bool:
    return bool(settings.bot_token.get_secret_value()) and settings.bot_mode == "webhook"


def head_revision() -> str | None:
    """The newest migration, read from the files without loading Alembic
    (a second of a cold start). None when the history is not a single line."""
    revisions: dict[str, str | None] = {}
    for path in (BACKEND / "migrations" / "versions").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        rev = re.search(r'^revision\b[^=]*=\s*"([^"]+)"', source, re.M)
        down = re.search(r'^down_revision\b[^=]*=\s*(?:"([^"]+)"|None)', source, re.M)
        if not rev or not down:
            return None
        revisions[rev.group(1)] = down.group(1)
    heads = set(revisions) - set(revisions.values())
    return heads.pop() if len(heads) == 1 else None


def _upgrade(connection: Connection) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def prepare_database() -> None:
    """Migrations, the demo catalog for a new database and the admins from
    ADMIN_TELEGRAM_IDS: one instance at a time, in one transaction."""
    settings = get_settings()
    head = head_revision()
    async with get_engine().begin() as conn:
        migrated = head is not None and bool(await conn.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL")))
        if migrated and await conn.scalar(text("SELECT version_num FROM alembic_version")) == head:
            # Already migrated (the usual case): no lock, no Alembic.
            async with AsyncSession(bind=conn) as session:
                await ensure_bootstrap_admins(session)
                await session.flush()
            return
        await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK})
        new_database = await conn.scalar(text("SELECT to_regclass('alembic_version') IS NULL"))
        if settings.auto_migrate:
            await conn.run_sync(_upgrade)
        async with AsyncSession(bind=conn) as session:
            if settings.auto_migrate and new_database:
                await seed_catalog(session)
            await ensure_bootstrap_admins(session)
            await session.flush()


def _instance_lock() -> asyncio.Lock:
    global _lock
    loop = asyncio.get_running_loop()
    if _lock is None or _lock[0] is not loop:
        _lock = (loop, asyncio.Lock())
    return _lock[1]


async def ensure_ready() -> bool:
    global _ready
    if not _ready:
        async with _instance_lock():
            if not _ready:
                try:
                    await prepare_database()
                except Exception:
                    log.exception("database is not ready")
                    return False
                _ready = True
    return True


async def _check_webhook() -> None:
    global _webhook_due_at
    if time.monotonic() < _webhook_due_at:
        return
    _webhook_due_at = math.inf
    from .bot import webhook

    try:
        await webhook.ensure_webhook()
    except Exception:
        _webhook_due_at = time.monotonic() + 300
        log.exception("could not register the bot webhook")


class ServerlessMiddleware:
    """Prepares the database before the first API request of the instance and
    does the background work after each request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        if not await ensure_ready():
            response = JSONResponse(UNAVAILABLE, status_code=503, headers={"Cache-Control": "no-store", "Retry-After": "30"})
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
        # The response is already sent: nothing below delays it.
        settings = get_settings()
        if settings.inline_worker:
            await inline.run_due(after_change=scope["method"] not in ("GET", "HEAD", "OPTIONS"))
        if bot_webhook_enabled(settings):
            await _check_webhook()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("api")
    yield
    await get_limiter().close()
    await dispose_engine()


def create_app() -> FastAPI:
    configure_environment(os.environ)
    get_settings.cache_clear()  # nothing may keep settings read before the defaults
    from .api.app import create_app as create_api_app

    app = create_api_app(lifespan_handler=lifespan)
    if bot_webhook_enabled(get_settings()):
        from .bot import webhook

        webhook.install(app)
    app.add_middleware(ServerlessMiddleware)
    return app


def reset() -> None:
    """Forget the state of this instance (tests)."""
    global _ready, _webhook_due_at
    _ready = False
    _webhook_due_at = 0.0
    inline.reset()
