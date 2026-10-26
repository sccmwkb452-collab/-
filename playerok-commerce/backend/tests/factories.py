"""Small builders for test data (only used by tests)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from autocommerce.database.enums import ComplianceStatus, DeliveryType, ProductStatus, PurchaseMode, SupplierStatus
from autocommerce.database.models import FxRate, Product, Supplier, SupplierProduct
from autocommerce.database.session import session_scope
from autocommerce.services import catalog, repricing
from autocommerce.services.audit import CLI
from autocommerce.shared.timeutil import utcnow


async def add_fx(currency: str = "USD", rate: str = "80.0000", day: datetime | None = None) -> None:
    async with session_scope() as s:
        s.add(FxRate(base=currency, quote="RUB", rate=Decimal(rate), source="cbr", rate_date=day or utcnow()))


async def make_product(
    *,
    name: str = "Steam Wallet 20 USD",
    category: str = "steam_cards",
    delivery: DeliveryType = DeliveryType.CODE,
    manual_cost: str | None = "1000",
    active: bool = True,
    **extra: Any,
) -> int:
    async with session_scope() as s:
        data = {"name": name, "category_code": category, "delivery_type": delivery.value, **extra}
        if manual_cost is not None:
            data["manual_unit_cost"] = manual_cost
        product = await catalog.create_product(s, data, CLI)
        await repricing.reprice_product(s, product, notify_owner=False)
        if active:
            product.status = ProductStatus.ACTIVE
        return product.id


async def make_supplier_item(
    supplier_code: str,
    *,
    external_id: str = "item-1",
    price: str = "10",
    currency: str = "USD",
    price_unit: int = 1,
    mode: PurchaseMode = PurchaseMode.CONFIRM,
    status: SupplierStatus = SupplierStatus.CONNECTED,
    compliance: ComplianceStatus = ComplianceStatus.APPROVED,
    raw: dict | None = None,
) -> int:
    async with session_scope() as s:
        supplier = (await s.execute(select(Supplier).where(Supplier.code == supplier_code))).scalar_one()
        supplier.purchase_mode = mode
        supplier.status = status
        sp = SupplierProduct(
            supplier_id=supplier.id,
            external_id=external_id,
            name=f"{supplier_code} {external_id}",
            price=Decimal(price),
            currency=currency,
            price_unit=price_unit,
            compliance_status=compliance,
            available=True,
            last_seen_at=utcnow(),
            raw=raw or {},
        )
        s.add(sp)
        await s.flush()
        return sp.id


async def link(product_id: int, supplier_product_id: int, **fields: Any) -> None:
    async with session_scope() as s:
        product = await s.get(Product, product_id)
        product.preferred_supplier_product_id = supplier_product_id
        for k, v in fields.items():
            setattr(product, k, v)
        await repricing.reprice_product(s, product, notify_owner=False)
