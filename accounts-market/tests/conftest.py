from __future__ import annotations

import os

os.environ.setdefault("TEST_DATABASE_URL", "postgresql+asyncpg://market:market@localhost:5432/market_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["PAYMENT_PROVIDER"] = "demo"
os.environ["DEMO_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["BOT_TOKEN"] = "42:TEST"
os.environ["ADMIN_IDS"] = "1"
os.environ["REDIS_URL"] = ""

import pytest
import pytest_asyncio
from sqlalchemy import text

from database.models import Base, Category, Product, User
from database.session import create_engine, create_sessionmaker
from catalog.manage import add_items
from services import shop_settings

ADMIN_ID = 1


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_size=20, max_overflow=10)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def sm(engine):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    sm = create_sessionmaker(engine)
    async with sm() as session:
        await shop_settings.ensure_defaults(session, "ACCOUNTS MARKET")
        await session.commit()
    return sm


@pytest_asyncio.fixture(loop_scope="session")
async def session(sm):
    async with sm() as s:
        yield s


async def make_user(sm, user_id: int, balance: int = 0, referrer_id: int | None = None, **kw) -> User:
    async with sm() as s, s.begin():
        user = User(id=user_id, username=f"u{user_id}", full_name=f"User {user_id}", balance=balance,
                    ref_code=f"code{user_id}", referrer_id=referrer_id, **kw)
        s.add(user)
    return user


async def make_product(sm, price: int = 1000_00, stock: int = 3, title: str = "Test product", **kw) -> Product:
    async with sm() as s, s.begin():
        category = Category(title=f"Cat {title}", emoji="🧪")
        s.add(category)
        await s.flush()
        product = Product(category_id=category.id, title=title, price=price, **kw)
        s.add(product)
        await s.flush()
        await add_items(s, product.id, [f"SECRET-{title}-{i}" for i in range(stock)])
    return product


def pytest_collection_modifyitems(items):
    import inspect

    marker = pytest.mark.asyncio(loop_scope="session")
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "function", None)) and "asyncio" not in item.keywords:
            item.add_marker(marker)
