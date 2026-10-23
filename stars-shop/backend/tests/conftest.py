"""Test fixtures. Tests run against a real PostgreSQL database
(TEST_DATABASE_URL, default postgresql+asyncpg://stars:stars@localhost:5432/stars_test);
the schema is created with the Alembic migrations, so migrations are tested too."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://stars:stars@localhost:5432/stars_test")
BOT_TOKEN = "123456789:AAtestTOKENtestTOKENtestTOKENtest12345"
os.environ.update(
    {
        "APP_ENV": "test",
        "APP_MODE": "demo",
        "DATABASE_URL": TEST_DB,
        "BOT_TOKEN": BOT_TOKEN,
        "BOT_USERNAME": "pulsar_test_bot",
        "SECRET_KEY": "test-secret-key-test-secret-key-0123456789",
        "PUBLIC_BASE_URL": "https://shop.test",
        "PAYMENT_PROVIDERS": "demo,cryptopay",
        "CRYPTOPAY_API_TOKEN": "1234:AAcryptopaytesttoken",
        "DELIVERY_PROVIDER": "demo",
        "RATE_LIMIT_ENABLED": "false",
        "ADMIN_TELEGRAM_IDS": "900001",
        "SHOP_CURRENCY": "RUB",
        "LOG_JSON": "false",
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

from starshop.api.app import create_app  # noqa: E402
from starshop.api.ratelimit import reset_limiter  # noqa: E402
from starshop.config import get_settings  # noqa: E402
from starshop.database.base import Base  # noqa: E402
from starshop.database.enums import AdminRole, ProductKind  # noqa: E402
from starshop.database.models import AdminUser, Product, User  # noqa: E402
from starshop.database.session import dispose_engine, get_sessionmaker, set_engine  # noqa: E402
from starshop.delivery import registry as delivery_registry  # noqa: E402
from starshop.payments import registry as payment_registry  # noqa: E402
from starshop.services import admin_auth  # noqa: E402
from starshop.services.app_settings import load_runtime_settings, save_setting  # noqa: E402
from starshop.shared.telegram_auth import sign_init_data  # noqa: E402

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
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def db_engine() -> AsyncIterator[None]:
    engine = create_async_engine(TEST_DB, poolclass=NullPool)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    set_engine(engine)
    payment_registry.reset_overrides()
    delivery_registry.reset_overrides()
    reset_limiter()
    yield
    await dispose_engine()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://shop.test") as c:
        yield c


def init_data(
    telegram_id: int = 100001,
    username: str | None = "buyer",
    *,
    start_param: str | None = None,
    auth_date: int | None = None,
    token: str = BOT_TOKEN,
) -> str:
    user: dict = {"id": telegram_id, "first_name": "Test", "language_code": "ru"}
    if username:
        user["username"] = username
    fields: dict = {"query_id": "AAH", "user": user, "auth_date": auth_date or int(time.time())}
    if start_param:
        fields["start_param"] = start_param
    return sign_init_data(fields, token)


def tma(telegram_id: int = 100001, username: str | None = "buyer", **kwargs) -> dict[str, str]:
    return {"Authorization": f"tma {init_data(telegram_id, username, **kwargs)}"}


def idem() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


@pytest.fixture
async def product(session: AsyncSession) -> Product:
    p = Product(kind=ProductKind.package, stars_amount=100, price=Decimal("169.00"), cost_per_star=Decimal("1.2000"), sort_order=10)
    session.add(p)
    await session.commit()
    return p


@pytest.fixture
async def custom_product(session: AsyncSession) -> Product:
    p = Product(kind=ProductKind.custom, title="Своё", price_per_star=Decimal("1.6500"), min_stars=50, max_stars=10_000, sort_order=100)
    session.add(p)
    await session.commit()
    return p


async def set_runtime(session: AsyncSession, key: str, **changes) -> None:
    runtime = await load_runtime_settings(session)
    value = getattr(runtime, key).model_dump(mode="json")
    value.update(changes)
    await save_setting(session, key, value, None)
    await session.commit()


async def make_admin(session: AsyncSession, role: AdminRole = AdminRole.owner, telegram_id: int = 900001) -> AdminUser:
    admin = AdminUser(telegram_id=telegram_id, role=role, is_active=True, display_name=f"{role} admin")
    session.add(admin)
    await session.commit()
    return admin


async def admin_client(
    client: httpx.AsyncClient, session: AsyncSession, role: AdminRole = AdminRole.owner, telegram_id: int = 900001
) -> dict[str, str]:
    """Logs in through the one-time link flow; returns CSRF headers."""
    admin = await make_admin(session, role, telegram_id)
    token = await admin_auth.issue_login_token(session, admin)
    await session.commit()
    r = await client.post("/api/v1/admin/auth/exchange", json={"token": token})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def get_user(session: AsyncSession, telegram_id: int) -> User:
    from sqlalchemy import select

    return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one()


async def create_order(
    client: httpx.AsyncClient,
    product_id: int,
    *,
    telegram_id: int = 100001,
    username: str | None = "buyer",
    recipient: dict | None = None,
    provider: str = "demo",
    **extra,
) -> dict:
    body = {"product_id": product_id, "recipient": recipient or {"type": "self"}, "payment_provider": provider, **extra}
    r = await client.post("/api/v1/orders", json=body, headers={**tma(telegram_id, username), **idem()})
    assert r.status_code == 201, r.text
    return r.json()


async def pay_demo(
    client: httpx.AsyncClient, order_id: str, *, telegram_id: int = 100001, username: str | None = "buyer", outcome: str = "success"
) -> dict:
    r = await client.post(f"/api/v1/orders/{order_id}/payment", json={"provider": "demo"}, headers=tma(telegram_id, username))
    assert r.status_code == 200, r.text
    payment = r.json()
    r = await client.post(f"/api/v1/demo/payments/{payment['id']}/complete", json={"outcome": outcome}, headers=tma(telegram_id, username))
    assert r.status_code == 200, r.text
    return payment
