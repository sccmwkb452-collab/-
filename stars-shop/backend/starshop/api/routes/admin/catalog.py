from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ....database.enums import ProductKind
from ....database.models import Product
from ....services import audit
from ....shared.errors import NotFound, ValidationFailed
from ....shared.items import PREMIUM_MONTHS
from ....shared.timeutil import utcnow
from ...deps import ManagerAdmin, SessionDep, SupportAdmin
from ...schemas import ProductIn, ProductPatch, ReorderIn
from ...serializers import product_admin

router = APIRouter(prefix="/products")


def _validate(p: Product) -> None:
    if p.kind == ProductKind.package:
        if not p.stars_amount or p.price is None:
            raise ValidationFailed("Для пакета укажите количество звёзд и цену", code="product_invalid")
    elif p.kind == ProductKind.premium:
        if p.premium_months not in PREMIUM_MONTHS or p.price is None:
            raise ValidationFailed("Для Telegram Premium укажите срок (3, 6 или 12 месяцев) и цену", code="product_invalid")
        if p.is_popular:
            raise ValidationFailed("Метка «Популярное» — только для пакетов звёзд", code="product_invalid")
    else:
        if not (p.price_per_star and p.min_stars and p.max_stars):
            raise ValidationFailed("Для произвольного количества укажите цену за звезду, минимум и максимум", code="product_invalid")
        if p.max_stars < p.min_stars:
            raise ValidationFailed("Максимум меньше минимума", code="product_invalid")


async def _unset_popular(session, except_id: int | None) -> None:
    stmt = update(Product).where(Product.is_popular.is_(True))
    if except_id is not None:
        stmt = stmt.where(Product.id != except_id)
    await session.execute(stmt.values(is_popular=False))


async def _get(session, product_id: int) -> Product:
    product = await session.get(Product, product_id)
    if product is None or product.is_archived:
        raise NotFound("Пакет не найден", code="product_not_found")
    return product


@router.get("")
async def list_products(ctx: SupportAdmin, session: SessionDep, include_archived: bool = False) -> dict:
    stmt = select(Product).order_by(Product.sort_order, Product.id)
    if not include_archived:
        stmt = stmt.where(Product.is_archived.is_(False))
    return {"items": [product_admin(p) for p in (await session.execute(stmt)).scalars()]}


@router.post("", status_code=201)
async def create_product(body: ProductIn, ctx: ManagerAdmin, session: SessionDep) -> dict:
    data = body.model_dump()
    if body.kind == ProductKind.package:
        data.update(price_per_star=None, min_stars=None, max_stars=None, premium_months=None, cost_price=None)
    elif body.kind == ProductKind.premium:
        data.update(stars_amount=None, price_per_star=None, min_stars=None, max_stars=None, cost_per_star=None)
    else:
        data.update(stars_amount=None, price=None, premium_months=None, cost_price=None)
    product = Product(**data)
    if body.cost_per_star is not None or body.cost_price is not None:
        product.cost_updated_at = utcnow()
    _validate(product)
    if product.is_popular:
        await _unset_popular(session, None)
    session.add(product)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ValidationFailed("Проверьте поля пакета", code="product_invalid") from exc
    await audit.record(
        session, ctx.admin, "product.create", entity_type="product", entity_id=product.id, after=product_admin(product), meta=ctx.meta
    )
    await session.commit()
    return product_admin(product)


@router.patch("/{product_id}")
async def patch_product(product_id: int, body: ProductPatch, ctx: ManagerAdmin, session: SessionDep) -> dict:
    product = await _get(session, product_id)
    before = product_admin(product)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(product, key, value)
    if "cost_per_star" in changes or "cost_price" in changes:
        product.cost_updated_at = utcnow()
    _validate(product)
    if changes.get("is_popular"):
        await _unset_popular(session, product.id)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ValidationFailed("Проверьте поля пакета", code="product_invalid") from exc
    await session.refresh(product)
    await audit.record(
        session,
        ctx.admin,
        "product.update",
        entity_type="product",
        entity_id=product.id,
        before=before,
        after=product_admin(product),
        meta=ctx.meta,
    )
    await session.commit()
    return product_admin(product)


@router.delete("/{product_id}")
async def delete_product(product_id: int, ctx: ManagerAdmin, session: SessionDep) -> dict:
    """Archive (soft delete): past orders keep referencing the product."""
    product = await _get(session, product_id)
    before = product_admin(product)
    product.is_archived = True
    product.is_active = False
    product.is_popular = False
    await audit.record(session, ctx.admin, "product.archive", entity_type="product", entity_id=product.id, before=before, meta=ctx.meta)
    await session.commit()
    return {"ok": True}


@router.post("/reorder")
async def reorder(body: ReorderIn, ctx: ManagerAdmin, session: SessionDep) -> dict:
    for index, product_id in enumerate(body.ids):
        await session.execute(update(Product).where(Product.id == product_id).values(sort_order=index * 10))
    await audit.record(session, ctx.admin, "product.reorder", entity_type="product", after={"ids": body.ids}, meta=ctx.meta)
    await session.commit()
    return {"ok": True}
