"""Products and categories."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ComplianceStatus, DeliveryType, ProductStatus
from ..database.models import Inventory, Product, ProductCategory, SupplierProduct
from ..shared.errors import Blocked, Conflict, DomainError, NotFound
from ..shared.money import money
from ..shared.timeutil import utcnow
from .audit import Actor, audit

EDITABLE = (
    "name",
    "description",
    "region",
    "face_value",
    "face_currency",
    "delivery_type",
    "delivery_time",
    "activation_notes",
    "buyer_instructions",
    "required_buyer_data",
    "supplier_quantity",
    "manual_unit_cost",
    "auto_purchase_allowed",
    "image_template",
)


def compliance_of(product: Product) -> ComplianceStatus:
    return product.compliance_override or product.category.compliance_status


def compliance_problem(product: Product) -> str | None:
    status = compliance_of(product)
    if status is ComplianceStatus.APPROVED:
        return None
    labels = {
        ComplianceStatus.NEEDS_REVIEW: "категория ждёт проверки правил платформы",
        ComplianceStatus.BLOCKED: "продажа запрещена правилами платформы",
        ComplianceStatus.NO_LEGAL_SOURCE: "нет легального канала закупки",
    }
    note = product.category.compliance_note
    return f"{labels[status]}: {note}" if note else labels[status]


async def get_category(session: AsyncSession, ref: int | str) -> ProductCategory:
    query = select(ProductCategory).where(ProductCategory.id == ref if isinstance(ref, int) else ProductCategory.code == ref)
    cat = (await session.execute(query)).scalar_one_or_none()
    if cat is None:
        raise NotFound("Категория не найдена")
    return cat


async def list_categories(session: AsyncSession) -> list[ProductCategory]:
    return list((await session.execute(select(ProductCategory).order_by(ProductCategory.sort, ProductCategory.id))).scalars())


async def update_category(session: AsyncSession, category: ProductCategory, data: dict[str, Any], actor: Actor) -> ProductCategory:
    before = {"commission": str(category.marketplace_commission_pct), "compliance": category.compliance_status.value}
    if "marketplace_commission_pct" in data:
        value = Decimal(str(data["marketplace_commission_pct"]))
        if not Decimal(0) <= value < Decimal(100):
            raise DomainError("Комиссия должна быть от 0 до 100 %")
        category.marketplace_commission_pct = value
        category.commission_source = str(data.get("commission_source") or f"изменено вручную: {actor.label}")[:255]
    if "compliance_status" in data:
        category.compliance_status = ComplianceStatus(data["compliance_status"])
        if data.get("compliance_note"):
            category.compliance_note = str(data["compliance_note"])[:2000]
    if "dispute_risk_pct" in data:
        category.dispute_risk_pct = Decimal(str(data["dispute_risk_pct"]))
    await audit(
        session,
        actor,
        "category.update",
        entity_type="category",
        entity_id=category.id,
        details={"before": before, "after": {k: str(v) for k, v in data.items()}},
    )
    return category


async def get_product(session: AsyncSession, product_id: int, *, lock: bool = False) -> Product:
    query = select(Product).where(Product.id == product_id)
    if lock:
        query = query.with_for_update(of=Product)
    product = (await session.execute(query)).unique().scalar_one_or_none()
    if product is None:
        raise NotFound("Товар не найден")
    return product


async def product_by_sku(session: AsyncSession, sku: str) -> Product | None:
    return (await session.execute(select(Product).where(Product.sku == sku))).unique().scalar_one_or_none()


def make_sku(name: str, category_code: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(_TRANSLIT)).strip("-")[:40] or "item"
    return f"{category_code}-{base}"


_TRANSLIT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
        "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
        "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)  # fmt: skip


async def create_product(session: AsyncSession, data: dict[str, Any], actor: Actor) -> Product:
    name = str(data.get("name") or "").strip()
    if len(name) < 3:
        raise DomainError("Название товара — минимум 3 символа")
    category = await get_category(session, data["category_id"] if "category_id" in data else data["category_code"])
    sku = str(data.get("sku") or make_sku(name, category.code))[:64]
    if await product_by_sku(session, sku):
        suffix = (await session.execute(select(func.count(Product.id)))).scalar_one() + 1
        sku = f"{sku[:58]}-{suffix}"
    product = Product(
        sku=sku,
        name=name[:200],
        category_id=category.id,
        status=ProductStatus.DRAFT,
        delivery_type=DeliveryType(data.get("delivery_type") or ("code" if category.auto_delivery_possible else "manual")),
    )
    product.category = category
    _apply(product, data)
    session.add(product)
    await session.flush()
    session.add(Inventory(product_id=product.id, unlimited=product.delivery_type is not DeliveryType.CODE))
    await audit(session, actor, "product.create", entity_type="product", entity_id=product.id, details={"sku": sku, "name": name})
    return product


def _apply(product: Product, data: dict[str, Any]) -> None:
    for key in EDITABLE:
        if key not in data:
            continue
        value = data[key]
        if key in ("face_value", "manual_unit_cost"):
            value = None if value in (None, "") else money(value)
            if key == "manual_unit_cost":
                product.manual_cost_updated_at = utcnow() if value is not None else None
        elif key == "delivery_type":
            value = DeliveryType(value)
        elif key == "supplier_quantity":
            value = max(1, int(value))
        elif key == "auto_purchase_allowed":
            value = bool(value)
        elif key == "image_template":
            value = (str(value).strip() or None) if value is not None else None
        elif isinstance(value, str):
            value = value.strip()
        setattr(product, key, value)


async def update_product(session: AsyncSession, product: Product, data: dict[str, Any], actor: Actor) -> Product:
    if data.get("auto_purchase_allowed") and compliance_of(product) is not ComplianceStatus.APPROVED:
        raise Blocked("Автозакупка разрешается только для товаров одобренных категорий")
    _apply(product, data)
    await audit(session, actor, "product.update", entity_type="product", entity_id=product.id, details={"fields": sorted(data)})
    return product


async def link_supplier_product(session: AsyncSession, product: Product, supplier_product_id: int | None, actor: Actor) -> Product:
    if supplier_product_id is not None:
        sp = await session.get(SupplierProduct, supplier_product_id)
        if sp is None:
            raise NotFound("Позиция поставщика не найдена")
    product.preferred_supplier_product_id = supplier_product_id
    await audit(
        session,
        actor,
        "product.link_supplier",
        entity_type="product",
        entity_id=product.id,
        details={"supplier_product_id": supplier_product_id},
    )
    return product


async def set_status(session: AsyncSession, product: Product, status: ProductStatus, actor: Actor, reason: str = "") -> Product:
    if status is ProductStatus.ACTIVE:
        problem = compliance_problem(product)
        if problem:
            raise Blocked(f"Нельзя активировать: {problem}")
    product.status = status
    await audit(
        session, actor, "product.status", entity_type="product", entity_id=product.id, details={"status": status.value, "reason": reason}
    )
    return product


async def create_from_supplier_item(session: AsyncSession, supplier_product: SupplierProduct, category_code: str, actor: Actor) -> Product:
    existing = (
        (await session.execute(select(Product).where(Product.preferred_supplier_product_id == supplier_product.id)))
        .unique()
        .scalar_one_or_none()
    )
    if existing:
        raise Conflict(f"Товар для этой позиции уже есть: {existing.name}")
    category = await get_category(session, category_code)
    raw = supplier_product.raw or {}
    delivery = (
        DeliveryType.CODE
        if supplier_product.supplier.adapter == "reloadly"
        else (DeliveryType.SERVICE if supplier_product.supplier.adapter == "smm_v2" else DeliveryType.MANUAL)
    )
    data: dict[str, Any] = {
        "name": supplier_product.name,
        "category_id": category.id,
        "region": supplier_product.region or "",
        "delivery_type": delivery.value,
    }
    if supplier_product.supplier.code == "fragment":
        data["required_buyer_data"] = "username Telegram получателя"
        data["delivery_time"] = "до 1 часа (закупка вручную)"
        if raw.get("quantity"):
            data["face_value"], data["face_currency"] = raw["quantity"], "STARS"
        elif raw.get("months"):
            data["face_value"], data["face_currency"] = raw["months"], "MONTHS"
    if delivery is DeliveryType.SERVICE:
        data["required_buyer_data"] = "ссылка на канал, пост или профиль"
        data["supplier_quantity"] = supplier_product.min_quantity or 1000
    if raw.get("unitPrice"):
        data["face_value"] = raw["unitPrice"]
        data["face_currency"] = raw.get("recipientCurrency")
    product = await create_product(session, data, actor)
    product.preferred_supplier_product_id = supplier_product.id
    return product


async def search_products(
    session: AsyncSession,
    *,
    query: str = "",
    category_id: int | None = None,
    group: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 10,
) -> tuple[list[Product], int]:
    stmt = select(Product).join(ProductCategory, Product.category_id == ProductCategory.id)
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if group:
        stmt = stmt.where(ProductCategory.group == group)
    if status:
        stmt = stmt.where(Product.status == ProductStatus(status))
    else:
        stmt = stmt.where(Product.status != ProductStatus.ARCHIVED)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(Product.id.desc()).offset((page - 1) * per_page).limit(per_page))).unique().scalars().all()
    return list(rows), total
