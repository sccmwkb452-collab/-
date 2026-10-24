"""Serverless hosting (Vercel): environment defaults, the database prepared on
the first request, background jobs after requests, the public DEMO identity
and the bot webhook."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from aiogram import Bot
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from starshop import serverless
from starshop.bot import webhook
from starshop.cli import DEMO_PACKAGES, DEMO_PREMIUM
from starshop.config import Settings, get_settings
from starshop.database.models import Notification, User
from starshop.database.session import set_engine
from starshop.shared.demo_identity import ID_BASE
from starshop.worker import inline
from tests.botkit import FakeSession, dispatcher
from tests.conftest import BACKEND, BOT_TOKEN, TEST_DB, idem, set_runtime

KEY = "visitor-key-0123456789abcdef"
DEMO = {"Authorization": f"demo {KEY}"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgresql://neondb_owner:p%40ss@ep-cool-1.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://neondb_owner:p%40ss@ep-cool-1.eu-central-1.aws.neon.tech/neondb?ssl=require",
        ),
        ("postgres://u:p@db.example:5432/shop", "postgresql+asyncpg://u:p@db.example:5432/shop"),
        ("postgresql+asyncpg://stars:stars@localhost:5432/stars", "postgresql+asyncpg://stars:stars@localhost:5432/stars"),
        ("postgresql://u:p@h/db?channel_binding=require", "postgresql+asyncpg://u:p@h/db"),
    ],
)
def test_database_urls_of_hosting_providers_use_asyncpg(raw, expected):
    assert Settings(database_url=raw).database_url == expected


def test_environment_defaults_prefer_explicit_values_and_direct_connection():
    env = {
        "DATABASE_URL": "postgresql://u:p@ep-1-pooler.neon.tech/db",
        "DATABASE_URL_UNPOOLED": "postgresql://u:p@ep-1.neon.tech/db",
        "VERCEL_URL": "pulsar-git-main.vercel.app",
        "VERCEL_PROJECT_PRODUCTION_URL": "pulsar.vercel.app",
        "APP_MODE": "production",
    }
    serverless.configure_environment(env)
    assert env["DATABASE_URL"] == "postgresql://u:p@ep-1.neon.tech/db"
    assert env["PUBLIC_BASE_URL"] == "https://pulsar.vercel.app"
    assert env["APP_MODE"] == "production"
    assert env["PUBLIC_DEMO"] == env["INLINE_WORKER"] == env["AUTO_MIGRATE"] == "true"
    assert env["DATABASE_POOL_SIZE"] == "0"
    assert re.fullmatch(r"[0-9a-f]{64}", env["SECRET_KEY"])

    again = {"DATABASE_URL_UNPOOLED": "postgresql://u:p@ep-1.neon.tech/db"}
    serverless.configure_environment(again)
    assert again["SECRET_KEY"] == env["SECRET_KEY"]  # stable between instances

    explicit = {
        "POSTGRES_URL": "postgresql://x",
        "SECRET_KEY": "own-secret",
        "PUBLIC_BASE_URL": "https://shop.example",
        "VERCEL_URL": "a.vercel.app",
    }
    serverless.configure_environment(explicit)
    assert (explicit["DATABASE_URL"], explicit["SECRET_KEY"], explicit["PUBLIC_BASE_URL"]) == (
        "postgresql://x",
        "own-secret",
        "https://shop.example",
    )


def test_vercel_requirements_pin_the_backend_versions():
    def pins(path) -> dict[str, str]:
        lines = [line.strip() for line in path.read_text().splitlines()]
        return {re.split(r"[\[=<>]", line)[0].lower(): line for line in lines if line and not line.startswith(("#", "-"))}

    backend, vercel = pins(BACKEND / "requirements.txt"), pins(BACKEND.parent / "api" / "requirements.txt")
    assert vercel
    assert {name: line for name, line in vercel.items() if backend.get(name) != line} == {}


# --- public DEMO identity ---------------------------------------------------


async def test_demo_identity_is_off_unless_public_demo(client):
    r = await client.get("/api/v1/me", headers=DEMO)
    assert r.status_code == 401


async def test_demo_visitor_gets_a_stable_identity_outside_telegram_ids(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "public_demo", True)
    first = (await client.get("/api/v1/me", headers=DEMO)).json()["user"]
    again = (await client.get("/api/v1/me", headers=DEMO)).json()["user"]
    other = (await client.get("/api/v1/me", headers={"Authorization": f"demo {KEY}-other"})).json()["user"]
    assert first == again
    assert ID_BASE <= first["telegram_id"] < 2**53  # never a Telegram user, exact in JavaScript
    assert re.fullmatch(r"demo_[0-9a-f]{8}", first["username"]) and first["first_name"] == "Гость"
    assert other["telegram_id"] != first["telegram_id"]

    r = await client.get("/api/v1/me", headers={"Authorization": "demo short"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "demo_key_invalid"
    # The admin panel accepts only Telegram-signed logins.
    assert (await client.get("/api/v1/admin/auth/me", headers=DEMO)).status_code == 401


async def test_demo_identity_stops_working_in_production_mode(client, settings, session, monkeypatch):
    monkeypatch.setattr(settings, "public_demo", True)
    await set_runtime(session, "shop", mode="production")
    r = await client.get("/api/v1/me", headers=DEMO)
    assert r.status_code == 401 and r.json()["error"]["code"] == "demo_identity_disabled"


# --- the serverless app ------------------------------------------------------


@pytest.fixture
def serverless_env() -> AsyncIterator[None]:
    saved = dict(os.environ)
    os.environ["BOT_MODE"] = "polling"
    serverless.reset()
    yield
    os.environ.clear()
    os.environ.update(saved)
    get_settings.cache_clear()
    serverless.reset()


@asynccontextmanager
async def vercel_client(**env: str) -> AsyncIterator[httpx.AsyncClient]:
    os.environ.update(env)
    app = serverless.create_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://shop.test") as c:
        yield c


async def test_demo_purchase_is_delivered_without_a_worker(serverless_env, product, session):
    async with vercel_client() as c:
        body = {"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"}
        r = await c.post("/api/v1/orders", json=body, headers={**DEMO, **idem()})
        assert r.status_code == 201, r.text
        order = r.json()
        payment = (await c.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=DEMO)).json()
        r = await c.post(f"/api/v1/demo/payments/{payment['id']}/complete", json={"outcome": "success"}, headers=DEMO)
        assert r.status_code == 200, r.text
        # The job ran after the payment request had been answered.
        r = await c.get(f"/api/v1/orders/{order['id']}", headers=DEMO)
        assert r.json()["status"] == "completed"
    user = (await session.execute(select(User).where(User.telegram_id >= ID_BASE))).scalar_one()
    assert await session.scalar(select(func.count()).select_from(Notification).where(Notification.chat_id == user.telegram_id)) == 0


async def test_inline_jobs_are_throttled_but_urgent_ones_follow_changes(monkeypatch):
    runs: list[str] = []

    def job(name: str):
        async def run() -> int:
            runs.append(name)
            return 0

        return run

    monkeypatch.setattr(inline, "JOBS", {"delivery": job("delivery"), "expiry": job("expiry")})
    inline.reset()
    await inline.run_due()
    await inline.run_due()  # within the intervals: nothing
    await inline.run_due(after_change=True)  # a payment may be waiting for delivery
    assert runs == ["delivery", "expiry", "delivery"]
    inline.reset()


async def test_api_answers_503_until_the_database_is_ready(serverless_env, monkeypatch):
    calls = []
    prepare = serverless.prepare_database

    async def flaky() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("connection refused")
        await prepare()

    monkeypatch.setattr(serverless, "prepare_database", flaky)
    async with vercel_client() as c:
        r = await c.get("/api/v1/bootstrap")
        assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable"
        assert (await c.get("/api/v1/bootstrap")).status_code == 200
        assert (await c.get("/api/v1/bootstrap")).status_code == 200
    assert len(calls) == 2  # prepared once per instance


def test_head_revision_matches_alembic():
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    assert serverless.head_revision() == ScriptDirectory.from_config(cfg).get_current_head()


def test_shop_pages_do_not_wait_for_the_bot_library():
    # aiogram takes seconds to import: only the bot webhook may load it.
    code = "import sys; from starshop import serverless; serverless.create_app(); print('aiogram' in sys.modules)"
    env = {**os.environ, "BOT_TOKEN": "123:abc", "DATABASE_URL": TEST_DB}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip().endswith("False")


async def test_new_database_is_migrated_and_seeded_once(settings, monkeypatch):
    monkeypatch.setattr(settings, "auto_migrate", True)
    schema = f"vercel_{uuid.uuid4().hex[:8]}"
    owner = create_async_engine(TEST_DB, poolclass=NullPool)
    async with owner.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(TEST_DB, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}})
    set_engine(engine)
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    try:
        # Two instances starting at the same moment.
        await asyncio.gather(serverless.prepare_database(), serverless.prepare_database())
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(cfg).get_current_head()
            assert await conn.scalar(text("SELECT count(*) FROM products")) == len(DEMO_PACKAGES) + 1 + len(DEMO_PREMIUM)
            assert await conn.scalar(text("SELECT count(*) FROM admin_users WHERE telegram_id = 900001 AND role = 'owner'")) == 1
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM products"))
        # At head: the next instance neither takes the lock nor loads Alembic.
        monkeypatch.setattr(serverless, "_upgrade", lambda conn: pytest.fail("migrated again"))
        await serverless.prepare_database()
        async with engine.connect() as conn:  # an emptied catalog is the owner's choice
            assert await conn.scalar(text("SELECT count(*) FROM products")) == 0
    finally:
        await engine.dispose()
        async with owner.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await owner.dispose()


class SetupApi:
    """Bot API for the webhook check (plain HTTP calls)."""

    def __init__(self) -> None:
        self.webhook: dict[str, Any] = {"url": "", "allowed_updates": None}
        self.menu: dict[str, Any] = {"type": "commands"}
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        result: Any = True
        if method == "getWebhookInfo":
            result = {**self.webhook, "has_custom_certificate": False, "pending_update_count": 0}
        elif method == "getChatMenuButton":
            result = self.menu
        elif method == "setWebhook":
            self.webhook = {"url": body["url"], "allowed_updates": body["allowed_updates"]}
        elif method == "setChatMenuButton":
            self.menu = body["menu_button"]
        return httpx.Response(200, json={"ok": True, "result": result})

    def made(self, method: str) -> list[dict]:
        return [body for m, body in self.calls if m == method]

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(webhook, "_api_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(self.handler)))


async def test_bot_works_through_the_webhook(serverless_env, session, monkeypatch):
    api = FakeSession()
    setup = SetupApi()
    setup.install(monkeypatch)
    monkeypatch.setattr(webhook, "new_bot", lambda: Bot(BOT_TOKEN, session=api))
    dispatcher()  # fresh FSM storage
    start = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": int(time.time()),
            "chat": {"id": 777, "type": "private"},
            "from": {"id": 777, "is_bot": False, "first_name": "Анна"},
            "text": "/start",
        },
    }
    async with vercel_client(BOT_MODE="webhook") as c:
        r = await c.post(webhook.PATH, json=start)
        assert r.status_code == 401
        r = await c.post(webhook.PATH, json=start, headers={"X-Telegram-Bot-Api-Secret-Token": webhook.webhook_secret()})
        assert r.status_code == 200, r.text

    assert api.texts(), "the bot answered /start"
    user = (await session.execute(select(User).where(User.telegram_id == 777))).scalar_one()
    assert user.bot_started
    hooks = setup.made("setWebhook")
    assert [(h["url"], h["secret_token"]) for h in hooks] == [("https://shop.test/api/v1/webhooks/telegram", webhook.webhook_secret())]
    assert set(hooks[0]["allowed_updates"]) == set(dispatcher().resolve_used_update_types())
    (menu,) = setup.made("setChatMenuButton")
    assert menu["menu_button"] == {"type": "web_app", "text": "🌐 Открыть магазин", "web_app": {"url": "https://shop.test/"}}
    assert [c["command"] for c in setup.made("setMyCommands")[0]["commands"]][:2] == ["start", "buy"]


async def test_webhook_check_refreshes_an_outdated_menu_button(serverless_env, monkeypatch):
    setup = SetupApi()
    setup.install(monkeypatch)
    await webhook.ensure_webhook()
    assert len(setup.made("setWebhook")) == 1
    await webhook.ensure_webhook()  # nothing changed: nothing is set again
    assert len(setup.made("setChatMenuButton")) == 1
    setup.menu = {"type": "web_app", "text": "Магазин", "web_app": {"url": "https://shop.test/"}}  # set by an older version
    await webhook.ensure_webhook()
    assert setup.menu["text"] == "🌐 Открыть магазин" and len(setup.made("setWebhook")) == 1


async def test_webhook_check_never_reports_the_token(serverless_env, monkeypatch):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}")

    monkeypatch.setattr(webhook, "_api_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(down)))
    with pytest.raises(RuntimeError) as exc:
        await webhook.ensure_webhook()
    assert BOT_TOKEN not in str(exc.value) and exc.value.__cause__ is None
