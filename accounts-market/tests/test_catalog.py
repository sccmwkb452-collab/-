from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import select

from catalog import service as catalog
from catalog.csv_import import import_csv
from database.models import Category, Product
from services.formatting import money, parse_rubles, parse_signed_rubles
from tests.conftest import make_product

CSV = """category;title;price;region;short_description;description;specs;items;featured
Новые товары;Ключ Pro;1490;EU;Кратко;Полное описание;Срок: 1 год|Почта: есть;KEY-1|KEY-2|KEY-3;1
Новые товары;Ключ Lite;99.50;;;;;KEY-L1;
;Без категории;100;;;;;;
Новые товары;Плохая цена;abc;;;;;;
""".encode()


async def test_csv_import_creates_and_updates(sm):
    async with sm() as s:
        report = await import_csv(s, CSV)
        await s.commit()
    assert (report.created, report.items, report.categories) == (2, 4, 1)
    assert len(report.errors) == 2
    async with sm() as s:
        pro = await s.scalar(select(Product).where(Product.title == "Ключ Pro"))
        assert pro.price == 1490_00 and pro.is_featured and pro.specs == "Срок: 1 год\nПочта: есть"
        assert await catalog.stock_count(s, pro.id) == 3
        lite = await s.scalar(select(Product).where(Product.title == "Ключ Lite"))
        assert lite.price == 99_50

    async with sm() as s:  # re-import: update price, append units, no duplicates
        report = await import_csv(s, "category,title,price,items\nНовые товары,ключ pro,1590,KEY-4".encode())
        await s.commit()
    assert (report.created, report.updated, report.items) == (0, 1, 1)
    async with sm() as s:
        pro = await s.scalar(select(Product).where(Product.title == "Ключ Pro"))
        assert pro.price == 1590_00 and await catalog.stock_count(s, pro.id) == 4
        assert len((await s.execute(select(Category))).scalars().all()) == 1


async def test_csv_requires_columns(sm):
    async with sm() as s:
        with pytest.raises(ValueError):
            await import_csv(s, b"name,cost\nx,1")


async def test_category_paging_puts_in_stock_first(sm):
    p_empty = await make_product(sm, title="Empty", stock=0)
    async with sm() as s:
        views, total = await catalog.category_products(s, p_empty.category_id, 0)
        assert total == 1 and views[0].stock == 0
        assert not catalog.is_buyable(views[0])


def test_money_formatting():
    assert money(1490_00) == "1 490 ₽"
    assert money(99_50) == "99,50 ₽"
    assert parse_rubles("1 490") == 1490_00
    assert parse_rubles("99,5") == 99_50
    assert parse_rubles("0") is None and parse_rubles("1.234") is None
    assert parse_signed_rubles("-200") == -200_00


def test_migrations_match_models():
    """alembic upgrade on an empty database, then `alembic check` finds no drift."""
    import asyncio

    import asyncpg

    url = os.environ["TEST_DATABASE_URL"]
    base, _, _ = url.rpartition("/")
    plain = base.replace("postgresql+asyncpg", "postgresql")

    async def recreate():
        conn = await asyncpg.connect(plain + "/postgres")
        await conn.execute("DROP DATABASE IF EXISTS market_migrations")
        await conn.execute("CREATE DATABASE market_migrations")
        await conn.close()

    asyncio.run(recreate())
    env = {**os.environ, "DATABASE_URL": base + "/market_migrations"}
    root = os.path.dirname(os.path.dirname(__file__))
    for args in (["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]):
        result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=root, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr[-2000:]


def test_countries_helpers():
    from catalog import countries

    assert countries.flag("de") == "🇩🇪" and countries.label("RU") == "🇷🇺 Россия"
    assert countries.parse("Германия") == "DE" and countries.parse("usa") == "US" and countries.parse("kz") == "KZ"
    assert countries.parse("Нарния") is None
    assert countries.search("гер", ["DE", "US"]) == ["DE"]
    assert countries.search("us", ["DE", "US"]) == ["US"]


async def test_country_offers_and_cheapest(sm):
    a = await make_product(sm, title="A", price=300_00, stock=2, country="RU")
    async with sm() as s, s.begin():
        s.add_all([
            Product(category_id=a.category_id, title="B", price=50_00, country="PH"),
            Product(category_id=a.category_id, title="C", price=200_00, country="RU"),
        ])
    async with sm() as s:
        b = await s.scalar(select(Product).where(Product.title == "B"))
        c = await s.scalar(select(Product).where(Product.title == "C"))
        from catalog.manage import add_items

        await add_items(s, c.id, ["x"])
        await s.commit()
        assert await catalog.has_countries(s, a.category_id)
        offers = await catalog.country_offers(s, a.category_id)
        assert [(o.code, o.min_price, o.stock, o.products) for o in offers] == [("RU", 200_00, 3, 2)]  # PH has no stock
        assert (await catalog.cheapest(s, a.category_id)).product.id == c.id
        views, total = await catalog.category_products(s, a.category_id, 0, country="RU")
        assert total == 2 and b.id not in [v.product.id for v in views]


async def test_csv_country_column(sm):
    async with sm() as s:
        report = await import_csv(s, "category,title,price,country,items\nВид,Позиция,10,Германия,K1\nВид,Другая,10,Нарния,K2".encode())
        await s.commit()
        assert report.created == 1 and "Нарния" in report.errors[0]
        assert (await s.scalar(select(Product).where(Product.title == "Позиция"))).country == "DE"
