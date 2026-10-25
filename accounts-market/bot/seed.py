"""Demo catalog for development: python -m bot.seed

Every demo product is marked `is_demo`, has «DEMO» in its title and delivers
a placeholder text, so it can never be mistaken for a real product.
Refuses to run with ENVIRONMENT=production.
"""

from __future__ import annotations

import asyncio
import secrets

from sqlalchemy import func, select

from bot.config import get_settings
from catalog.manage import add_items
from database.models import Category, Product
from database.session import create_engine, create_sessionmaker
from services import shop_settings

CATEGORIES = [
    ("🆕", "Новые товары", "Свежие позиции без истории использования.", 10),
    ("📅", "Товары с историей", "Позиции с подтверждённым сроком использования.", 20),
    ("🌍", "Региональные товары", "Позиции, привязанные к определённому региону.", 30),
    ("📦", "Другие цифровые товары", "Ключи, лицензии и прочее.", 40),
]

PRODUCTS = [
    # category index, title, price (rub), region, short, specs, stock, featured
    (0, "DEMO · Premium-аккаунт на 12 месяцев", 1490, "EU", "Новый аккаунт с подпиской на год",
     "Срок подписки: 12 месяцев\nПочта: в комплекте\nГарантия: 24 часа", 12, True),
    (0, "DEMO · Стандартный аккаунт", 390, None, "Базовый аккаунт для старта",
     "Тип: стандарт\nПочта: в комплекте", 25, False),
    (0, "DEMO · Аккаунт с подпиской на 1 месяц", 290, "Global", "Подписка на 30 дней",
     "Срок подписки: 1 месяц", 0, False),
    (1, "DEMO · Аккаунт со стажем 1 год", 990, "US", "Создан более 12 месяцев назад",
     "Стаж: 1 год\nПочта: в комплекте\nДвухфакторная защита: отключена", 6, True),
    (1, "DEMO · Аккаунт со стажем 3 года", 2490, "US", "Проверенная история активности",
     "Стаж: 3 года\nПочта: в комплекте", 3, False),
    (2, "DEMO · Региональный аккаунт DE", 690, "Германия", "Регион аккаунта: Германия",
     "Регион: DE\nЯзык интерфейса: немецкий", 8, False),
    (2, "DEMO · Региональный аккаунт TR", 590, "Турция", "Регион аккаунта: Турция",
     "Регион: TR", 5, False),
    (2, "DEMO · Региональный аккаунт KZ", 540, "Казахстан", "Регион аккаунта: Казахстан",
     "Регион: KZ", 4, False),
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
            await add_items(
                session,
                product.id,
                [f"DEMO-{secrets.token_hex(4).upper()} · демо-данные, не являются реальным товаром" for _ in range(stock)],
            )
    await engine.dispose()
    print(f"Demo catalog created: {len(CATEGORIES)} categories, {len(PRODUCTS)} products")


if __name__ == "__main__":
    asyncio.run(seed())
