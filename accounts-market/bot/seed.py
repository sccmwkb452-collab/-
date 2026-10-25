"""Demo catalog for development: python -m bot.seed

Every demo product is marked `is_demo`, has «DEMO» in its title and delivers
a placeholder text, so it can never be mistaken for a real product.
Refuses to run with ENVIRONMENT=production.
"""

from __future__ import annotations

import asyncio
import random
import secrets

from sqlalchemy import func, select

from bot.config import get_settings
from catalog.countries import name as country_name
from catalog.manage import add_items
from database.models import Category, Product
from database.session import create_engine, create_sessionmaker
from services import shop_settings

CATEGORIES = [
    ("🆕", "Новые", "свежая позиция, выдача сразу после оплаты", 10),
    ("📅", "С историей", "позиция с подтверждённым сроком использования", 20),
    ("⭐", "Премиум", "с активной премиум-подпиской сервиса", 30),
    ("📦", "Другие товары", "ключи, коды и прочие цифровые товары", 40),
]

# Base price (rubles) per country; categories 0-2 are browsed through the country grid.
COUNTRIES = {
    "RU": 300, "US": 420, "PH": 47, "ZA": 120, "TR": 90, "CL": 110, "MX": 95, "EG": 60,
    "BD": 55, "NG": 50, "KZ": 150, "DE": 390, "GB": 410, "IN": 70, "BR": 140, "ID": 65,
}
VARIANTS = [
    # category index, title template, price multiplier, short description, specs
    (0, "DEMO · Подписка Standard", 1.0, "Новая позиция с подпиской на 30 дней",
     "Срок подписки: 30 дней\nПочта: в комплекте\nГарантия: 24 часа"),
    (1, "DEMO · Аккаунт со стажем 1 год", 2.5, "Создан более 12 месяцев назад",
     "Стаж: от 12 месяцев\nПочта: в комплекте"),
    (2, "DEMO · Подписка Premium", 4.0, "Активная премиум-подписка на 12 месяцев",
     "Срок подписки: 12 месяцев\nПочта: в комплекте\nГарантия: 48 часов"),
]

PRODUCTS = [
    # category index, title, price (rub), region, short, specs, stock, featured
    (3, "DEMO · Лицензионный ключ Pro", 1190, None, "Ключ активации, выдаётся сразу",
     "Тип: ключ активации\nСрок: бессрочно", 30, True),
    (3, "DEMO · Подарочный код 500 ₽", 520, "RU", "Цифровой подарочный код",
     "Номинал: 500 ₽", 15, False),
    (3, "DEMO · Набор шаблонов", 150, None, "Цифровой набор для скачивания",
     "Формат: ZIP по ссылке", 50, False),
]

DESCRIPTION = (
    "Это демонстрационная позиция для проверки магазина. После «покупки» выдаётся "
    "текстовая заглушка, а не реальный товар."
)


async def seed() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Demo data cannot be seeded with ENVIRONMENT=production")
    engine = create_engine(settings.database_url)
    sm = create_sessionmaker(engine)
    async with sm() as session, session.begin():
        await shop_settings.ensure_defaults(session, settings.shop_name)
        if await session.scalar(select(func.count(Product.id)).where(Product.is_demo.is_(True))):
            print("Demo catalog already exists, nothing to do")
            return
        categories = []
        for emoji, title, description, order in CATEGORIES:
            category = await session.scalar(select(Category).where(Category.title == title))
            if category is None:
                category = Category(emoji=emoji, title=title, description=description, sort_order=order)
                session.add(category)
                await session.flush()
            categories.append(category)
        rng = random.Random(7)
        for cat, title, factor, short, specs in VARIANTS:
            for code, base in COUNTRIES.items():
                product = Product(
                    category_id=categories[cat].id,
                    title=f"{title} · {country_name(code)}",
                    price=int(base * factor) * 100,
                    country=code,
                    short_description=short,
                    description=DESCRIPTION,
                    specs=specs,
                    is_featured=code in ("RU", "US") and cat == 0,
                    is_demo=True,
                )
                session.add(product)
                await session.flush()
                await add_items(session, product.id, [_demo_unit() for _ in range(rng.randint(3, 25))])
        for cat, title, price, region, short, specs, stock, featured in PRODUCTS:
            product = Product(
                category_id=categories[cat].id,
                title=title,
                price=price * 100,
                region=region,
                short_description=short,
                description=DESCRIPTION,
                specs=specs,
                is_featured=featured,
                is_demo=True,
            )
            session.add(product)
            await session.flush()
            await add_items(session, product.id, [_demo_unit() for _ in range(stock)])
    await engine.dispose()
    total = len(VARIANTS) * len(COUNTRIES) + len(PRODUCTS)
    print(f"Demo catalog created: {len(CATEGORIES)} categories, {total} products")


def _demo_unit() -> str:
    return f"DEMO-{secrets.token_hex(4).upper()} · демо-данные, не являются реальным товаром"


if __name__ == "__main__":
    asyncio.run(seed())
