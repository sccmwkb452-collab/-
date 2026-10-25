"""Write side of the catalog, used by the admin panel."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Category, ItemStatus, Product, ProductItem

MAX_ITEM_LENGTH = 3500


def split_items(raw: str) -> list[str]:
    """One unit per non-empty line. Units longer than a Telegram message are rejected."""
    items = [line.strip() for line in raw.replace("\r\n", "\n").split("\n")]
    items = [i for i in items if i]
    too_long = [i for i in items if len(i) > MAX_ITEM_LENGTH]
    if too_long:
        raise ValueError(f"Единица товара длиннее {MAX_ITEM_LENGTH} символов")
    return items


async def add_items(session: AsyncSession, product_id: int, contents: list[str]) -> int:
    session.add_all(ProductItem(product_id=product_id, content=c) for c in contents)
    await session.flush()
    return len(contents)


async def withdraw_available(session: AsyncSession, product_id: int) -> int:
    result = await session.execute(
        update(ProductItem)
        .where(ProductItem.product_id == product_id, ProductItem.status == ItemStatus.AVAILABLE)
        .values(status=ItemStatus.WITHDRAWN)
    )
    return result.rowcount or 0


async def stock_breakdown(session: AsyncSession, product_id: int) -> dict[str, int]:
    rows = await session.execute(
        select(ProductItem.status, func.count(ProductItem.id))
        .where(ProductItem.product_id == product_id)
        .group_by(ProductItem.status)
    )
    counts = {s: 0 for s in (ItemStatus.AVAILABLE, ItemStatus.SOLD, ItemStatus.REVOKED, ItemStatus.WITHDRAWN)}
    counts.update({s: int(n) for s, n in rows.all()})
    return counts


async def create_product(
    session: AsyncSession, category_id: int, title: str, price: int, short_description: str
) -> Product:
    product = Product(category_id=category_id, title=title, price=price, short_description=short_description)
    session.add(product)
    await session.flush()
    return product


async def category_by_title(session: AsyncSession, title: str) -> Category | None:
    return await session.scalar(select(Category).where(func.lower(Category.title) == title.strip().lower()))


async def products_in_category(session: AsyncSession, category_id: int) -> int:
    return int(await session.scalar(select(func.count(Product.id)).where(Product.category_id == category_id)) or 0)
