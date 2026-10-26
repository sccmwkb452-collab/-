from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...database.enums import CodeStatus, ProductStatus
from ...database.models import DigitalCode, MarketPriceSnapshot, SupplierProduct
from ...services import analytics, catalog, inventory, repricing, research
from ...shared.errors import NotFound
from .. import serializers as ser
from ..deps import Context, need

router = APIRouter(tags=["catalog"])


@router.get("/categories")
async def categories(ctx: Context = Depends(need("view"))) -> dict:
    return {"items": [ser.category(c) for c in await catalog.list_categories(ctx.session)]}


class CategoryIn(BaseModel):
    marketplace_commission_pct: Decimal | None = Field(default=None, ge=0, lt=100)
    commission_source: str | None = Field(default=None, max_length=255)
    compliance_status: str | None = None
    compliance_note: str | None = Field(default=None, max_length=2000)
    dispute_risk_pct: Decimal | None = Field(default=None, ge=0, le=100)


@router.patch("/categories/{category_id}")
async def update_category(category_id: int, body: CategoryIn, ctx: Context = Depends(need("products.manage"))) -> dict:
    cat = await catalog.get_category(ctx.session, category_id)
    await catalog.update_category(ctx.session, cat, body.model_dump(exclude_none=True), ctx.actor)
    return ser.category(cat)


@router.get("/products")
async def products(
    q: str = Query("", max_length=100),
    category_id: int | None = None,
    group: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    ctx: Context = Depends(need("view")),
) -> dict:
    rows, total = await catalog.search_products(
        ctx.session, query=q, category_id=category_id, group=group, status=status, page=page, per_page=per_page
    )
    return {"items": [ser.product(p) for p in rows], "total": total, "page": page, "per_page": per_page}


class ProductIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    category_id: int
    sku: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=4000)
    region: str = Field(default="", max_length=64)
    face_value: Decimal | None = None
    face_currency: str | None = Field(default=None, max_length=8)
    delivery_type: str = "manual"
    delivery_time: str = Field(default="до 30 минут", max_length=120)
    activation_notes: str = Field(default="", max_length=2000)
    buyer_instructions: str = Field(default="", max_length=2000)
    required_buyer_data: str = Field(default="", max_length=255)
    supplier_quantity: int = Field(default=1, ge=1, le=10_000_000)
    manual_unit_cost: Decimal | None = Field(default=None, ge=0)


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    region: str | None = Field(default=None, max_length=64)
    face_value: Decimal | None = None
    face_currency: str | None = Field(default=None, max_length=8)
    delivery_type: str | None = None
    delivery_time: str | None = Field(default=None, max_length=120)
    activation_notes: str | None = Field(default=None, max_length=2000)
    buyer_instructions: str | None = Field(default=None, max_length=2000)
    required_buyer_data: str | None = Field(default=None, max_length=255)
    supplier_quantity: int | None = Field(default=None, ge=1, le=10_000_000)
    manual_unit_cost: Decimal | None = Field(default=None, ge=0)
    auto_purchase_allowed: bool | None = None
    image_template: str | None = Field(default=None, max_length=64)


@router.post("/products")
async def create_product(body: ProductIn, ctx: Context = Depends(need("products.manage"))) -> dict:
    product = await catalog.create_product(ctx.session, body.model_dump(exclude_none=True), ctx.actor)
    await repricing.reprice_product(ctx.session, product, actor=ctx.actor, notify_owner=False)
    return ser.product(product)


class FromSupplierIn(BaseModel):
    supplier_product_id: int
    category_code: str = Field(max_length=64)


@router.post("/products/from-supplier")
async def from_supplier(body: FromSupplierIn, ctx: Context = Depends(need("products.manage"))) -> dict:
    sp = await ctx.session.get(SupplierProduct, body.supplier_product_id)
    if sp is None:
        raise NotFound("Позиция поставщика не найдена")
    product = await catalog.create_from_supplier_item(ctx.session, sp, body.category_code, ctx.actor)
    await repricing.reprice_product(ctx.session, product, actor=ctx.actor, notify_owner=False)
    return ser.product(product)


async def _detail(ctx: Context, product_id: int) -> dict[str, Any]:
    product = await catalog.get_product(ctx.session, product_id)
    result, cost, policy = await repricing.evaluate_product(ctx.session, product)
    snaps = (
        await ctx.session.execute(
            select(MarketPriceSnapshot)
            .where(MarketPriceSnapshot.product_id == product.id)
            .order_by(MarketPriceSnapshot.observed_at.desc())
            .limit(10)
        )
    ).scalars()
    sp = await ctx.session.get(SupplierProduct, product.preferred_supplier_product_id) if product.preferred_supplier_product_id else None
    from ...database.models import ResearchScore

    score = await ctx.session.get(ResearchScore, product.id)
    return {
        **ser.product(product, stock=await inventory.stock(ctx.session, product.id)),
        "category_full": ser.category(product.category),
        "calculation": result.as_dict(),
        "cost_source": cost.source,
        "cost_currency": cost.purchase_currency,
        "fx_rate": ser.d(cost.fx_rate),
        "policy": policy.to_values(),
        "supplier_product": ser.supplier_product(sp) if sp else None,
        "observations": [ser.snapshot(s) for s in snaps],
        "research": {
            "total_score": ser.d(score.total_score),
            "confidence": score.confidence.value,
            "factors": score.factors,
            "computed_at": ser.dt(score.computed_at),
        }
        if score
        else None,
        "price_dynamics": await analytics.price_dynamics(ctx.session, product.id),
    }


@router.get("/products/{product_id}")
async def product_detail(product_id: int, ctx: Context = Depends(need("view"))) -> dict:
    return await _detail(ctx, product_id)


@router.patch("/products/{product_id}")
async def update_product(product_id: int, body: ProductPatch, ctx: Context = Depends(need("products.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, product_id, lock=True)
    await catalog.update_product(ctx.session, product, body.model_dump(exclude_none=True), ctx.actor)
    await repricing.reprice_product(ctx.session, product, actor=ctx.actor)
    return await _detail(ctx, product_id)


class StatusIn(BaseModel):
    status: ProductStatus
    reason: str = Field(default="", max_length=500)


@router.post("/products/{product_id}/status")
async def product_status(product_id: int, body: StatusIn, ctx: Context = Depends(need("products.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, product_id, lock=True)
    await catalog.set_status(ctx.session, product, body.status, ctx.actor, body.reason)
    return ser.product(product)


@router.post("/products/{product_id}/reprice")
async def reprice(product_id: int, ctx: Context = Depends(need("view"))) -> dict:
    product = await catalog.get_product(ctx.session, product_id)
    await repricing.reprice_product(ctx.session, product, actor=ctx.actor)
    await research.compute(ctx.session, product)
    return await _detail(ctx, product_id)


class PriceIn(BaseModel):
    price: Decimal = Field(gt=0, le=10_000_000)


@router.post("/products/{product_id}/price")
async def set_price(product_id: int, body: PriceIn, ctx: Context = Depends(need("pricing.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, product_id)
    result = await repricing.apply_price(ctx.session, product, body.price, ctx.actor)
    return {"product": ser.product(product), "calculation": result.as_dict()}


class LinkIn(BaseModel):
    supplier_product_id: int | None


@router.post("/products/{product_id}/link-supplier")
async def link_supplier(product_id: int, body: LinkIn, ctx: Context = Depends(need("products.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, product_id, lock=True)
    await catalog.link_supplier_product(ctx.session, product, body.supplier_product_id, ctx.actor)
    await repricing.reprice_product(ctx.session, product, actor=ctx.actor)
    return await _detail(ctx, product_id)


class ObservationIn(BaseModel):
    competitor_min: Decimal = Field(gt=0)
    competitor_median: Decimal | None = Field(default=None, gt=0)
    competitor_max: Decimal | None = Field(default=None, gt=0)
    offers_count: int | None = Field(default=None, ge=0, le=100_000)
    note: str = Field(default="", max_length=1000)


@router.post("/products/{product_id}/observations")
async def add_observation(product_id: int, body: ObservationIn, ctx: Context = Depends(need("pricing.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, product_id)
    await research.add_observation(ctx.session, product, body.model_dump(), ctx.actor)
    await repricing.reprice_product(ctx.session, product, actor=ctx.actor)
    await research.compute(ctx.session, product)
    return await _detail(ctx, product_id)


@router.get("/products/{product_id}/codes")
async def product_codes(product_id: int, status: str | None = None, ctx: Context = Depends(need("inventory.manage"))) -> dict:
    stmt = select(DigitalCode).where(DigitalCode.product_id == product_id).order_by(DigitalCode.id.desc()).limit(200)
    if status:
        stmt = stmt.where(DigitalCode.status == CodeStatus(status))
    rows = (await ctx.session.execute(stmt)).scalars()
    return {"items": [ser.code(c) for c in rows], "stock": await inventory.stock(ctx.session, product_id)}


class CodesIn(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=1000)
    unit_cost: Decimal | None = Field(default=None, ge=0)


@router.post("/products/{product_id}/codes")
async def import_codes(product_id: int, body: CodesIn, ctx: Context = Depends(need("inventory.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, product_id)
    result = await inventory.add_codes(ctx.session, product, body.codes, ctx.actor, unit_cost=body.unit_cost)
    return {
        "added": result.added,
        "duplicates": result.duplicates,
        "rejected": result.rejected,
        "stock": await inventory.stock(ctx.session, product_id),
    }


@router.post("/codes/{code_id}/reveal")
async def reveal_code(code_id: int, ctx: Context = Depends(need("orders.reveal_codes"))) -> dict:
    code, plain = await inventory.reveal(ctx.session, code_id, ctx.actor)
    return {"id": code.id, "code": plain, "status": code.status.value}


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/codes/{code_id}/void")
async def void_code(code_id: int, body: VoidIn, ctx: Context = Depends(need("inventory.manage"))) -> dict:
    code = await inventory.void_code(ctx.session, code_id, ctx.actor, body.reason)
    return ser.code(code)
