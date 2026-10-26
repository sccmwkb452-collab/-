"""Applies the pricing engine to products stored in the database.

* policy: global rule → category rule → product rule (each overrides fields);
* cost: the linked supplier position (price × units ÷ price unit, supplier
  fee, FX) or the manual cost entered by the operator;
* market: the latest competitor observation.

Guards: a listing is never left on sale below its minimum price or with a
stale purchase price without the owner knowing — the listing is blocked
and a notification explains what to change on PlayerOK.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ListingStatus, Severity
from ..database.models import Listing, MarketPriceSnapshot, PriceRule, Product, Supplier, SupplierProduct
from ..integrations.marketplace.playerok_manual import get_marketplace
from ..shared.errors import Blocked
from ..shared.money import fmt_money, money
from ..shared.timeutil import local_today, utcnow
from . import fx
from .audit import SYSTEM, Actor, audit
from .notifications import btn, esc, notify
from .pricing import STATUS_LABELS, CostInput, MarketInput, PricingPolicy, PricingResult, calculate


async def global_policy(session: AsyncSession) -> PricingPolicy:
    rule = (await session.execute(select(PriceRule).where(PriceRule.scope == "global"))).scalar_one_or_none()
    return PricingPolicy.from_values(rule.values if rule and rule.enabled else {})


async def resolve_policy(session: AsyncSession, product: Product) -> PricingPolicy:
    policy = await global_policy(session)
    rules = (
        await session.execute(
            select(PriceRule).where(
                PriceRule.enabled.is_(True),
                ((PriceRule.scope == "category") & (PriceRule.category_id == product.category_id))
                | ((PriceRule.scope == "product") & (PriceRule.product_id == product.id)),
            )
        )
    ).scalars()
    by_scope = {r.scope: r for r in rules}
    for scope in ("category", "product"):
        if scope in by_scope:
            policy = PricingPolicy.from_values(by_scope[scope].values, base=policy)
    return policy


async def save_rule(
    session: AsyncSession,
    scope: str,
    values: dict[str, Any],
    actor: Actor,
    *,
    category_id: int | None = None,
    product_id: int | None = None,
) -> PriceRule:
    base = PricingPolicy() if scope == "global" else await global_policy(session)
    PricingPolicy.from_values(values, base=base)  # validates
    clean = {k: (None if v in (None, "") else str(v)) for k, v in values.items() if k in PricingPolicy.FIELDS}
    query = select(PriceRule).where(PriceRule.scope == scope)
    if scope == "category":
        query = query.where(PriceRule.category_id == category_id)
    elif scope == "product":
        query = query.where(PriceRule.product_id == product_id)
    rule = (await session.execute(query)).scalar_one_or_none()
    if rule is None:
        rule = PriceRule(scope=scope, category_id=category_id, product_id=product_id, values={})
        session.add(rule)
    merged = dict(rule.values or {})
    merged.update(clean)
    if scope != "global":
        merged = {k: v for k, v in merged.items() if v is not None}
    rule.values = merged
    rule.enabled = True
    await audit(
        session, actor, "price_rule.save", entity_type="price_rule", entity_id=f"{scope}:{category_id or product_id or ''}", details=clean
    )
    return rule


async def cost_input(session: AsyncSession, product: Product) -> CostInput:
    commission = product.category.marketplace_commission_pct
    if product.preferred_supplier_product_id:
        sp = await session.get(SupplierProduct, product.preferred_supplier_product_id)
        if sp is not None and sp.price is not None and sp.available:
            supplier: Supplier = sp.supplier
            units = Decimal(product.supplier_quantity or 1)
            per_unit = sp.price * units / Decimal(sp.price_unit or 1)
            rate = await fx.latest_rate(session, sp.currency)
            return CostInput(
                purchase_price=per_unit,
                purchase_currency=sp.currency,
                fx_rate=rate[0] if rate else None,
                fx_date=rate[1] if rate else None,
                supplier_fee_pct=supplier.fee_pct,
                supplier_fee_fixed=supplier.fee_fixed,
                marketplace_commission_pct=commission,
                price_captured_at=sp.last_seen_at,
                source=f"{supplier.name}: {sp.name}",
            )
    if product.manual_unit_cost is not None:
        return CostInput(
            purchase_price=product.manual_unit_cost,
            purchase_currency="RUB",
            marketplace_commission_pct=commission,
            price_captured_at=product.manual_cost_updated_at,
            source="себестоимость указана вручную",
        )
    return CostInput(purchase_price=None, marketplace_commission_pct=commission)


async def market_input(session: AsyncSession, product_id: int) -> tuple[MarketInput | None, MarketPriceSnapshot | None]:
    snap = (
        await session.execute(
            select(MarketPriceSnapshot)
            .where(MarketPriceSnapshot.product_id == product_id)
            .order_by(MarketPriceSnapshot.observed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snap is None:
        return None, None
    return MarketInput(snap.competitor_min, snap.competitor_median, snap.offers_count, snap.observed_at), snap


async def evaluate_product(
    session: AsyncSession, product: Product, *, now: datetime | None = None
) -> tuple[PricingResult, CostInput, PricingPolicy]:
    policy = await resolve_policy(session, product)
    cost = await cost_input(session, product)
    market, _ = await market_input(session, product.id)
    result = calculate(cost, policy, current_price=product.current_price, market=market, now=now)
    return result, cost, policy


async def reprice_product(session: AsyncSession, product: Product, *, actor: Actor = SYSTEM, notify_owner: bool = True) -> PricingResult:
    result, cost, _ = await evaluate_product(session, product)
    product.min_price = result.min_price
    product.recommended_price = result.recommended_price
    product.full_cost = result.breakdown.full_cost if result.breakdown else None
    product.expected_profit = result.recommended.net_profit if result.recommended else None
    product.expected_margin_pct = result.recommended.margin_pct if result.recommended else None
    product.pricing_status = result.status
    product.pricing_notes = result.notes + ([f"Источник цены: {cost.source}"] if cost.source else [])
    product.priced_at = utcnow()
    await guard_listings(session, product, result, notify_owner=notify_owner)
    return result


async def guard_listings(session: AsyncSession, product: Product, result: PricingResult, *, notify_owner: bool = True) -> list[Listing]:
    """Block listings that would sell at a loss or on stale data."""
    listings = (
        (
            await session.execute(
                select(Listing).where(Listing.product_id == product.id, Listing.status.in_([ListingStatus.READY, ListingStatus.PUBLISHED]))
            )
        )
        .unique()
        .scalars()
        .all()
    )
    affected: list[Listing] = []
    market = get_marketplace()
    for listing in listings:
        problem: str | None = None
        if not result.can_sell:
            problem = STATUS_LABELS.get(result.status, result.status) + ". " + " ".join(result.notes)
        elif result.min_price is not None and listing.price < result.min_price:
            problem = f"Цена объявления {fmt_money(listing.price)} ниже минимальной {fmt_money(result.min_price)}"
        if problem is None:
            continue
        affected.append(listing)
        was_published = listing.status is ListingStatus.PUBLISHED
        listing.status = ListingStatus.BLOCKED
        listing.status_reason = problem[:2000]
        if not notify_owner:
            continue
        action = "Публикация остановлена."
        if was_published:
            if market.supports("update_listings") and listing.external_id:
                action = "Объявление будет приостановлено через интеграцию."
            else:
                action = "⚠️ Объявление уже на PlayerOK: снимите его с продажи или поменяйте цену вручную."
        rec = f"\nРекомендуемая цена: <b>{fmt_money(result.recommended_price)}</b>" if result.can_sell and result.recommended_price else ""
        buttons = [[btn("📝 Открыть объявление", f"lst:open:{listing.id}"), btn("💰 Пересчитать", f"prd:reprice:{product.id}")]]
        if result.can_sell and result.recommended_price:
            buttons.insert(0, [btn("📋 Скопировать цену", copy=str(money(result.recommended_price)))])
        await notify(
            session,
            "price_alert",
            f"Защита от убытка: {product.name}",
            f"{esc(problem)}\n{action}{rec}",
            severity=Severity.WARNING,
            buttons=buttons,
            entity_type="listing",
            entity_id=listing.id,
            dedupe_key=f"price_guard:{listing.id}:{result.status}:{local_today().isoformat()}",
        )
    return affected


async def apply_price(session: AsyncSession, product: Product, new_price: Decimal, actor: Actor) -> PricingResult:
    """Set the selling price. Refuses prices below the minimum and stale data.
    The product row is locked (and versioned), so two concurrent price
    changes cannot both win."""
    new_price = money(new_price)
    # lock only the product row (FOR UPDATE cannot cover the outer-joined category)
    await session.execute(select(Product.id).where(Product.id == product.id).with_for_update())
    await session.refresh(product)
    result, _, _ = await evaluate_product(session, product)
    if not result.can_sell:
        raise Blocked(f"Цена не изменена: {STATUS_LABELS.get(result.status, result.status)}. {' '.join(result.notes)}")
    if result.min_price is not None and new_price < result.min_price:
        raise Blocked(f"Цена {fmt_money(new_price)} ниже минимальной {fmt_money(result.min_price)} — продажа была бы убыточной по правилам")
    old = product.current_price
    product.current_price = new_price
    await audit(
        session, actor, "product.price", entity_type="product", entity_id=product.id, details={"old": str(old), "new": str(new_price)}
    )
    return calculate(
        await cost_input(session, product),
        await resolve_policy(session, product),
        current_price=new_price,
        market=(await market_input(session, product.id))[0],
    )
