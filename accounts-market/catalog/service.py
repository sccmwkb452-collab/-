"""Read side of the catalog: categories, products, stock counters."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Category, ItemStatus, Order, OrderStatus, Product, ProductItem

PAGE_SIZE = 5


@dataclass(frozen=True)
class ProductView:
    product: Product
    stock: int
    sold: int = 0


def _stock_subquery():
    return (
        select(ProductItem.product_id, func.count(ProductItem.id).label("stock"))
        .where(ProductItem.status == ItemStatus.AVAILABLE)
        .group_by(ProductItem.product_id)
        .subquery()
    )


def _sold_subquery():
    return (
        select(Order.product_id, func.count(Order.id).label("sold"))
        .where(Order.status == OrderStatus.COMPLETED)
        .group_by(Order.product_id)
        .subquery()
    )


async def active_categories(session: AsyncSession) -> list[tuple[Category, int]]:
    """Visible categories with the number of products that are on sale."""
    stock = _stock_subquery()
    counts = (
        select(Product.category_id, func.count(Product.id).label("n"))
        .join(stock, stock.c.product_id == Product.id)
        .where(Product.is_archived.is_(False), stock.c.stock > 0)
        .group_by(Product.category_id)
        .subquery()
    )
    rows = await session.execute(
        select(Category, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.category_id == Category.id)
        .where(Category.is_active.is_(True))
        .order_by(Category.sort_order, Category.id)
    )
    return [(c, int(n)) for c, n in rows.all()]


async def category_products(
    session: AsyncSession, category_id: int, page: int, page_size: int = PAGE_SIZE
) -> tuple[list[ProductView], int]:
    """Products of a category, in-stock first. Returns (page items, total count)."""
    stock = _stock_subquery()
    cond = and_(Product.category_id == category_id, Product.is_archived.is_(False))
    total = await session.scalar(select(func.count(Product.id)).where(cond)) or 0
    stock_col = func.coalesce(stock.c.stock, 0)
    rows = await session.execute(
        select(Product, stock_col)
        .outerjoin(stock, stock.c.product_id == Product.id)
        .where(cond)
        .order_by((stock_col > 0).desc(), Product.is_featured.desc(), Product.price, Product.id)
        .limit(page_size)
        .offset(page * page_size)
    )
    return [ProductView(p, int(s)) for p, s in rows.all()], int(total)


async def popular_products(session: AsyncSession, limit: int = 6) -> list[ProductView]:
    """Featured items first, then best sellers; only what can be bought right now."""
    stock, sold = _stock_subquery(), _sold_subquery()
    sold_col = func.coalesce(sold.c.sold, 0)
    rows = await session.execute(
        select(Product, stock.c.stock, sold_col)
        .join(stock, stock.c.product_id == Product.id)
        .join(Category, Category.id == Product.category_id)
        .outerjoin(sold, sold.c.product_id == Product.id)
        .where(Product.is_archived.is_(False), stock.c.stock > 0, Category.is_active.is_(True))
        .order_by(Product.is_featured.desc(), sold_col.desc(), Product.id)
        .limit(limit)
    )
    return [ProductView(p, int(s), int(n)) for p, s, n in rows.all()]


async def get_product(session: AsyncSession, product_id: int) -> ProductView | None:
    product = await session.get(Product, product_id)
    if product is None:
        return None
    return ProductView(product, await stock_count(session, product_id))


async def stock_count(session: AsyncSession, product_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count(ProductItem.id)).where(
                ProductItem.product_id == product_id, ProductItem.status == ItemStatus.AVAILABLE
            )
        )
        or 0
    )


def is_buyable(view: ProductView) -> bool:
    p = view.product
    return not p.is_archived and p.category.is_active and view.stock > 0


def parse_specs(specs: str) -> list[tuple[str, str]]:
    result = []
    for line in specs.splitlines():
        line = line.strip().lstrip("•-").strip()
        if not line:
            continue
        name, sep, value = line.partition(":")
        result.append((name.strip(), value.strip()) if sep else ("", line))
    return result
