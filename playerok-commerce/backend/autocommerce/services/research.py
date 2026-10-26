"""Market Research: ranking of product opportunities.

Every factor carries its value, the basis (where the number comes from), the
date of the data and a confidence level. Demand is «high confidence» only when
it is based on our own completed sales. Competitor offers observed on
PlayerOK are an *indirect* signal and are never presented as sales.
Factors without data are left out of the weighted total instead of being
guessed.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import CONFIDENCE_LABELS, ComplianceStatus, Confidence, DeliveryType, OrderStatus, ProductStatus
from ..database.models import MarketPriceSnapshot, Order, OrderItem, Product, ResearchScore, Supplier, SupplierPriceHistory, SupplierProduct
from ..integrations.suppliers import registry
from ..shared.timeutil import utcnow
from . import app_settings
from .catalog import compliance_of
from .pricing import CostInput, calculate
from .repricing import evaluate_product, global_policy, market_input

ORDER = [Confidence.NONE, Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]


def _factor(score: float | None, value: Any, basis: str, confidence: Confidence, at: Any = None) -> dict[str, Any]:
    return {
        "score": None if score is None else round(max(0.0, min(100.0, score)), 1),
        "value": value,
        "basis": basis,
        "confidence": confidence.value,
        "confidence_label": CONFIDENCE_LABELS[confidence],
        "at": at.isoformat() if hasattr(at, "isoformat") else at,
    }


async def compute(session: AsyncSession, product: Product) -> ResearchScore:
    now = utcnow()
    since = now - timedelta(days=30)
    factors: dict[str, dict[str, Any]] = {}
    status = compliance_of(product)
    excluded: str | None = None
    if status in (ComplianceStatus.BLOCKED, ComplianceStatus.NO_LEGAL_SOURCE):
        excluded = f"Исключено: {product.category.compliance_note or status.value}"

    # own sales
    rows = (
        await session.execute(
            select(Order.status, Order.placed_at, Order.completed_at, OrderItem.quantity)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.product_id == product.id, Order.placed_at >= since, Order.is_test.is_(False))
        )
    ).all()
    completed = [r for r in rows if r.status is OrderStatus.COMPLETED]
    problems = [r for r in rows if r.status in (OrderStatus.REFUND, OrderStatus.DISPUTE)]
    units = sum(r.quantity for r in completed)
    market, snap = await market_input(session, product.id)

    if completed:
        conf = Confidence.HIGH if len(completed) >= 5 else Confidence.MEDIUM
        factors["demand"] = _factor(min(100, 20 + units * 8), f"{units} шт. за 30 дней", "собственные завершённые продажи", conf, now)
    elif market is not None and market.offers_count is not None:
        score = 30 if market.offers_count == 0 else min(60, 25 + market.offers_count * 2)
        factors["demand"] = _factor(
            score,
            f"{market.offers_count} предложений конкурентов",
            "косвенный признак: число предложений на PlayerOK (это не продажи)",
            Confidence.LOW,
            market.observed_at,
        )
    else:
        factors["demand"] = _factor(None, None, "нет данных: нет продаж и наблюдений рынка", Confidence.NONE)

    result, cost, policy = await evaluate_product(session, product)
    if result.recommended is not None:
        conf = Confidence.HIGH if (market and market.observed_at) and result.status == "ok" else Confidence.MEDIUM
        if result.status == "stale_price":
            conf = Confidence.LOW
        factors["margin"] = _factor(
            float(result.recommended.margin_pct) * 3,
            f"{result.recommended.margin_pct:.1f} % / {result.recommended.net_profit} ₽",
            f"Pricing Engine: {cost.source or 'нет источника'}",
            conf,
            cost.price_captured_at,
        )
    else:
        factors["margin"] = _factor(None, None, "нет себестоимости или курса", Confidence.NONE)

    durations = [(r.completed_at - r.placed_at).total_seconds() / 3600 for r in completed if r.completed_at]
    if durations:
        avg_h = statistics.mean(durations)
        score = 100 if avg_h <= 1 else 80 if avg_h <= 6 else 60 if avg_h <= 24 else 35 if avg_h <= 72 else 15
        factors["turnover"] = _factor(score, f"{avg_h:.1f} ч от заказа до завершения", "собственные сделки", Confidence.MEDIUM, now)
    else:
        factors["turnover"] = _factor(None, None, "нет завершённых сделок", Confidence.NONE)

    if market is not None and market.offers_count is not None:
        n = market.offers_count
        score = 90 if n <= 5 else 60 if n <= 20 else 35 if n <= 50 else 15
        factors["competition"] = _factor(
            score, f"{n} предложений", f"наблюдение: {snap.source if snap else 'оператор'}", Confidence.LOW, market.observed_at
        )
    else:
        factors["competition"] = _factor(None, None, "нет наблюдений рынка", Confidence.NONE)

    sp = await session.get(SupplierProduct, product.preferred_supplier_product_id) if product.preferred_supplier_product_id else None
    if sp is not None:
        prices = (
            (
                await session.execute(
                    select(SupplierPriceHistory.price).where(
                        SupplierPriceHistory.supplier_product_id == sp.id, SupplierPriceHistory.captured_at >= since
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(prices) >= 2:
            values = [float(p) for p in prices]
            cv = statistics.pstdev(values) / statistics.mean(values) if statistics.mean(values) else 0
            factors["supplier_stability"] = _factor(
                100 - min(100, cv * 500),
                f"колебание {cv * 100:.1f} %",
                f"история цен {sp.supplier.name} за 30 дней",
                Confidence.MEDIUM,
                now,
            )
        else:
            factors["supplier_stability"] = _factor(None, f"{len(prices)} точек", "мало истории цен", Confidence.NONE)
        supplier: Supplier = sp.supplier
        total_ops = supplier.success_count + supplier.error_count
        if total_ops >= 3:
            rate = supplier.success_count / total_ops
            factors["supplier_reliability"] = _factor(
                rate * 100,
                f"{rate * 100:.0f} % успешных операций",
                f"{supplier.name}: {total_ops} операций",
                Confidence.MEDIUM,
                supplier.last_check_at,
            )
        else:
            factors["supplier_reliability"] = _factor(None, None, f"{supplier.name}: мало операций для оценки", Confidence.NONE)
        age = (now - sp.last_seen_at) if sp.last_seen_at else None
        if age is not None:
            hours = age.total_seconds() / 3600
            score = 100 if hours <= 1 else 80 if hours <= 6 else 50 if hours <= 24 else 10
            factors["freshness"] = _factor(
                score, f"{hours:.1f} ч назад", f"последняя синхронизация {supplier.name}", Confidence.HIGH, sp.last_seen_at
            )
        can_buy = registry.adapter_class(supplier.adapter).capabilities.purchase
    else:
        can_buy = False
        if product.manual_cost_updated_at:
            hours = (now - product.manual_cost_updated_at).total_seconds() / 3600
            factors["freshness"] = _factor(
                100 if hours <= 6 else 50 if hours <= 48 else 10,
                f"{hours:.1f} ч назад",
                "себестоимость введена вручную",
                Confidence.MEDIUM,
                product.manual_cost_updated_at,
            )

    order_count = len(rows)
    if order_count >= 5:
        risk = len(problems) / order_count * 100
        factors["dispute_risk"] = _factor(
            100 - risk * 4, f"{risk:.1f} % возвратов и споров", f"собственные заказы: {order_count}", Confidence.MEDIUM, now
        )
    else:
        risk = float(product.category.dispute_risk_pct)
        factors["dispute_risk"] = _factor(
            100 - risk * 4, f"≈{risk:.0f} %", "экспертная оценка категории (мало своих данных)", Confidence.LOW
        )

    if product.delivery_type is DeliveryType.CODE:
        auto = (100, "коды от поставщика с API") if can_buy else (70, "коды со склада")
    elif product.delivery_type is DeliveryType.SERVICE:
        auto = (80, "услуга выполняется поставщиком по API") if can_buy else (30, "услуга вручную")
    else:
        auto = (20, "ручная выдача")
    factors["auto_delivery"] = _factor(auto[0], auto[1], "тип выдачи и возможности поставщика", Confidence.HIGH)

    restrictions = {
        ComplianceStatus.APPROVED: "разрешено",
        ComplianceStatus.NEEDS_REVIEW: "нужна проверка правил платформы",
        ComplianceStatus.BLOCKED: "запрещено правилами",
        ComplianceStatus.NO_LEGAL_SOURCE: "нет легального канала закупки",
    }[status]
    factors["restrictions"] = {
        "score": None,
        "value": restrictions,
        "basis": product.category.compliance_note,
        "confidence": "high",
        "confidence_label": "высокая",
        "at": None,
    }

    weights = await app_settings.get_setting(session, "research.weights")
    total_w, total = 0.0, 0.0
    for key, weight in weights.items():
        f = factors.get(key)
        if not f or f["score"] is None or not weight:
            continue
        score = f["score"] if key != "dispute_risk" else f["score"]
        total += score * weight
        total_w += weight
    total_score = total / total_w if total_w else 0.0
    if status is ComplianceStatus.NEEDS_REVIEW:
        total_score *= 0.6
    key_conf = [Confidence(factors[k]["confidence"]) for k in ("demand", "margin")]
    confidence = min(key_conf, key=ORDER.index)
    row = await session.get(ResearchScore, product.id)
    if row is None:
        row = ResearchScore(product_id=product.id, total_score=Decimal(0), confidence=confidence)
        session.add(row)
    row.total_score = Decimal(str(round(total_score, 2)))
    row.confidence = confidence
    row.factors = factors
    row.excluded_reason = excluded
    row.computed_at = now
    _ = policy
    return row


async def add_observation(session: AsyncSession, product: Product, data: dict[str, Any], actor: Any) -> MarketPriceSnapshot:
    """Competitor prices seen on PlayerOK by the operator (with date and note)."""
    from ..shared.errors import DomainError
    from ..shared.money import money
    from .audit import audit

    def opt(key: str) -> Decimal | None:
        value = data.get(key)
        return None if value in (None, "") else money(value)

    lo, med, hi = opt("competitor_min"), opt("competitor_median"), opt("competitor_max")
    if lo is None:
        raise DomainError("Укажите минимальную цену конкурентов")
    if med is not None and med < lo or hi is not None and hi < (med or lo):
        raise DomainError("Цены должны идти по возрастанию: минимум ≤ медиана ≤ максимум")
    offers = data.get("offers_count")
    snap = MarketPriceSnapshot(
        product_id=product.id,
        source="manual",
        competitor_min=lo,
        competitor_median=med,
        competitor_max=hi,
        offers_count=None if offers in (None, "") else max(0, int(offers)),
        note=str(data.get("note") or "")[:1000],
        recorded_by=getattr(actor, "label", None),
        observed_at=utcnow(),
    )
    session.add(snap)
    await session.flush()
    await audit(
        session,
        actor,
        "market.observation",
        entity_type="product",
        entity_id=product.id,
        details={"min": str(lo), "offers": snap.offers_count},
    )
    return snap


async def recompute_all(session: AsyncSession) -> int:
    products = (await session.execute(select(Product).where(Product.status != ProductStatus.ARCHIVED))).unique().scalars().all()
    for product in products:
        await compute(session, product)
    return len(products)


async def ranking(
    session: AsyncSession, *, include_excluded: bool = False, limit: int = 50, offset: int = 0
) -> tuple[list[tuple[Product, ResearchScore]], int]:
    stmt = select(Product, ResearchScore).join(ResearchScore, ResearchScore.product_id == Product.id)
    if not include_excluded:
        stmt = stmt.where(ResearchScore.excluded_reason.is_(None))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(ResearchScore.total_score.desc()).offset(offset).limit(limit))).unique().all()
    return [(p, s) for p, s in rows], total


async def supplier_opportunities(
    session: AsyncSession, *, limit: int = 30, offset: int = 0, search: str = ""
) -> tuple[list[dict[str, Any]], int]:
    """Supplier positions without a product yet: purchase cost in RUB and the
    minimum PlayerOK price that would meet the profit rules. Compare it with
    PlayerOK prices yourself — competitor prices are not collected automatically."""
    from . import fx

    policy = await global_policy(session)
    linked = select(Product.preferred_supplier_product_id).where(Product.preferred_supplier_product_id.is_not(None))
    stmt = (
        select(SupplierProduct)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(SupplierProduct.available.is_(True), SupplierProduct.price.is_not(None), SupplierProduct.id.not_in(linked))
    )
    if search:
        stmt = stmt.where(SupplierProduct.name.ilike(f"%{search}%"))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        (await session.execute(stmt.order_by(SupplierProduct.supplier_id, SupplierProduct.id).offset(offset).limit(limit)))
        .unique()
        .scalars()
        .all()
    )
    out = []
    for sp in rows:
        rate = await fx.latest_rate(session, sp.currency)
        unit = Decimal(sp.min_quantity or 1000) if sp.price_unit > 1 else Decimal(1)
        per_sale = (sp.price or Decimal(0)) * unit / Decimal(sp.price_unit or 1)
        commission = Decimal("10") if sp.supplier.code in ("fragment", "reloadly") else Decimal("20")
        result = calculate(
            CostInput(
                purchase_price=per_sale,
                purchase_currency=sp.currency,
                fx_rate=rate[0] if rate else None,
                supplier_fee_pct=sp.supplier.fee_pct,
                marketplace_commission_pct=commission,
                price_captured_at=sp.last_seen_at,
            ),
            policy,
        )
        out.append(
            {
                "id": sp.id,
                "supplier": sp.supplier.name,
                "supplier_code": sp.supplier.code,
                "name": sp.name,
                "category": sp.category,
                "price": str(sp.price),
                "currency": sp.currency,
                "units_per_sale": int(unit),
                "cost_rub": str(result.breakdown.full_cost) if result.breakdown else None,
                "min_price": str(result.min_price) if result.min_price else None,
                "target_price": str(result.target_price) if result.target_price else None,
                "status": result.status,
                "compliance": sp.compliance_status.value,
                "checked_at": sp.last_seen_at.isoformat() if sp.last_seen_at else None,
                "note": "Сравните минимальную цену с ценами на PlayerOK вручную: данные конкурентов не собираются автоматически",
            }
        )
    return out, total
