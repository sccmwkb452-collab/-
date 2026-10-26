"""Test fixtures. Tests run against a real PostgreSQL database
(TEST_DATABASE_URL, default postgresql+asyncpg://pac:pac@localhost:5432/pac_test).
The schema is created by the Alembic migrations, so migrations are tested too.
The local .env is never read (PAC_ENV_FILE is empty), external HTTP goes
through httpx.MockTransport and Telegram through a fake sender."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://pac:pac@localhost:5432/pac_test")
BOT_TOKEN = "123456789:AAtestTOKENtestTOKENtestTOKENtest12345"
OWNER_ID = 900001
STORAGE = Path(tempfile.mkdtemp(prefix="pac-test-storage-"))
os.environ.update(
    {
        "PAC_ENV_FILE": "",
        "APP_ENV": "test",
        "APP_MODE": "test",
        "ALLOW_LIVE_OPERATIONS": "true",
        "DATABASE_URL": TEST_DB,
        "BOT_TOKEN": BOT_TOKEN,
        "BOT_USERNAME": "pac_test_bot",
        "OWNER_TELEGRAM_IDS": str(OWNER_ID),
        "SECRET_KEY": "test-secret-key-test-secret-key-0123456789",
        "RATE_LIMIT_ENABLED": "false",
        "LOG_JSON": "false",
        "STORAGE_DIR": str(STORAGE),
        "VEXBOOST_API_KEY": "",
        "RELOADLY_CLIENT_ID": "",
        "RELOADLY_CLIENT_SECRET": "",
    }
)
os.environ.pop("REDIS_URL", None)

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from autocommerce.config import reset_settings_cache  # noqa: E402

reset_settings_cache()

from autocommerce.api.security import reset_limiter  # noqa: E402
from autocommerce.database.base import Base  # noqa: E402
from autocommerce.database.session import dispose_engine, get_sessionmaker, session_scope, set_engine  # noqa: E402
from autocommerce.integrations import http as integration_http  # noqa: E402
from autocommerce.integrations.marketplace.playerok_manual import PlayerokManualAdapter, set_marketplace  # noqa: E402
from autocommerce.integrations.suppliers import registry  # noqa: E402
from autocommerce.services import bootstrap, notifications  # noqa: E402
from autocommerce.services.notifications import SendResult, TelegramSender  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> None:
    import asyncio

    async def reset_schema() -> None:
        engine = create_async_engine(TEST_DB, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset_schema())
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["database_url"] = TEST_DB
    cfg.attributes["skip_logging"] = True
    command.upgrade(cfg, "head")


class FakeSender(TelegramSender):
    def __init__(self) -> None:
        super().__init__(token=BOT_TOKEN)
        self.sent: list[tuple[int, str, list | None]] = []
        self.script: list[SendResult] = []

    async def send_message(self, chat_id: int, text: str, buttons=None) -> SendResult:
        if self.script:
            result = self.script.pop(0)
            if not result.ok:
                return result
        self.sent.append((chat_id, text, buttons))
        return SendResult(True)


@pytest.fixture(autouse=True)
async def db_engine() -> AsyncIterator[None]:
    engine = create_async_engine(TEST_DB, poolclass=NullPool)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await conn.execute(text("ALTER SEQUENCE order_number_seq RESTART WITH 1"))
    set_engine(engine)
    registry.reset_overrides()
    integration_http.set_transport(None)
    set_marketplace(PlayerokManualAdapter())
    reset_limiter()
    yield
    integration_http.set_transport(None)
    notifications.set_sender(None)
    await dispose_engine()


@pytest.fixture
def sender() -> FakeSender:
    fake = FakeSender()
    notifications.set_sender(fake)
    return fake


@pytest.fixture
async def seeded() -> None:
    async with session_scope() as session:
        await bootstrap.seed(session)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as s:
        yield s


def mock_http(handler) -> None:
    integration_http.set_transport(httpx.MockTransport(handler))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from autocommerce.api.app import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://panel.test") as c:
        yield c
