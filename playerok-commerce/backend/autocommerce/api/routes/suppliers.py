from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ...database.enums import ComplianceStatus, PurchaseMode
from ...database.models import SupplierOrder, SupplierProduct
from ...integrations.suppliers import registry
from ...services import credentials, suppliers
from ...services.audit import audit
from ...shared.errors import NotFound
from .. import serializers as ser
from ..deps import Context, need

router = APIRouter(tags=["suppliers"])


@router.get("/suppliers")
async def list_suppliers(ctx: Context = Depends(need("view"))) -> dict:
    from ...database.models import Supplier

    rows = (await ctx.session.execute(select(Supplier).order_by(Supplier.id))).scalars()
    out = []
    for s in rows:
        spent, ops = await suppliers.spent_today(ctx.session, s.id)
        count = (await ctx.session.execute(select(func.count()).where(SupplierProduct.supplier_id == s.id))).scalar_one()
        out.append({**ser.supplier(s), "spent_today_rub": str(spent), "operations_today": ops, "products_count": count})
    return {"items": out}


@router.get("/suppliers/{supplier_id}")
async def detail(supplier_id: int, ctx: Context = Depends(need("view"))) -> dict:
    s = await suppliers.get_supplier(ctx.session, supplier_id)
    cls = registry.adapter_class(s.adapter)
    history = (
        await ctx.session.execute(
            select(SupplierOrder).where(SupplierOrder.supplier_id == s.id).order_by(SupplierOrder.id.desc()).limit(30)
        )
    ).scalars()
    spent, ops = await suppliers.spent_today(ctx.session, s.id)
    return {
        **ser.supplier(s),
        "credentials": await credentials.describe(ctx.session, s.code, cls.credential_fields),
        "orders": [ser.supplier_order(o) for o in history],
        "spent_today_rub": str(spent),
        "operations_today": ops,
    }


@router.get("/suppliers/{supplier_id}/products")
async def products(
    supplier_id: int,
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    ctx: Context = Depends(need("view")),
) -> dict:
    stmt = select(SupplierProduct).where(SupplierProduct.supplier_id == supplier_id)
    if q:
        stmt = stmt.where(SupplierProduct.name.ilike(f"%{q}%"))
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(SupplierProduct.id).offset((page - 1) * per_page).limit(per_page))).unique().scalars()
    return {"items": [ser.supplier_product(sp) for sp in rows], "total": total, "page": page, "per_page": per_page}


@router.post("/suppliers/{supplier_id}/check")
async def check(supplier_id: int, ctx: Context = Depends(need("suppliers.manage"))) -> dict:
    s = await suppliers.get_supplier(ctx.session, supplier_id)
    result = await suppliers.check_connection(ctx.session, s, ctx.actor)
    return {"ok": result.ok, "message": result.message, "supplier": ser.supplier(s)}


@router.post("/suppliers/{supplier_id}/sync")
async def sync(supplier_id: int, ctx: Context = Depends(need("suppliers.manage"))) -> dict:
    s = await suppliers.get_supplier(ctx.session, supplier_id)
    run = await suppliers.sync_catalog(ctx.session, s, force=True)
    return {"run": ser.sync_run(run) if run else None, "supplier": ser.supplier(s)}


class SupplierPatch(BaseModel):
    purchase_mode: PurchaseMode | None = None
    max_single_purchase: Decimal | None = Field(default=None, ge=0)
    daily_limit: Decimal | None = Field(default=None, ge=0)
    max_operations_per_day: int | None = Field(default=None, ge=0, le=10_000)
    fee_pct: Decimal | None = Field(default=None, ge=0, lt=100)
    fee_fixed: Decimal | None = Field(default=None, ge=0)
    enabled: bool | None = None


@router.patch("/suppliers/{supplier_id}")
async def update(supplier_id: int, body: SupplierPatch, ctx: Context = Depends(need("suppliers.manage"))) -> dict:
    s = await suppliers.get_supplier(ctx.session, supplier_id)
    await suppliers.set_mode(ctx.session, s, body.model_dump(exclude_none=True), ctx.actor)
    return ser.supplier(s)


class CredentialsIn(BaseModel):
    values: dict[str, str]


@router.put("/suppliers/{supplier_id}/credentials")
async def save_credentials(supplier_id: int, body: CredentialsIn, ctx: Context = Depends(need("suppliers.manage"))) -> dict:
    s = await suppliers.get_supplier(ctx.session, supplier_id)
    cls = registry.adapter_class(s.adapter)
    await credentials.save_credentials(ctx.session, s.code, cls.credential_fields, body.values, ctx.actor)
    result = await suppliers.check_connection(ctx.session, s, ctx.actor)
    return {
        "ok": result.ok,
        "message": result.message,
        "credentials": await credentials.describe(ctx.session, s.code, cls.credential_fields),
    }


@router.delete("/suppliers/{supplier_id}/credentials")
async def delete_credentials(supplier_id: int, ctx: Context = Depends(need("suppliers.manage"))) -> dict:
    s = await suppliers.get_supplier(ctx.session, supplier_id)
    await credentials.delete_credentials(ctx.session, s.code, ctx.actor)
    return {"ok": True}


class ComplianceIn(BaseModel):
    compliance_status: ComplianceStatus


@router.patch("/supplier-products/{sp_id}")
async def supplier_product_compliance(sp_id: int, body: ComplianceIn, ctx: Context = Depends(need("suppliers.manage"))) -> dict:
    sp = await ctx.session.get(SupplierProduct, sp_id)
    if sp is None:
        raise NotFound("Позиция не найдена")
    sp.compliance_status = body.compliance_status
    await audit(
        ctx.session,
        ctx.actor,
        "supplier_product.compliance",
        entity_type="supplier_product",
        entity_id=sp.id,
        details={"status": body.compliance_status.value},
    )
    return ser.supplier_product(sp)
