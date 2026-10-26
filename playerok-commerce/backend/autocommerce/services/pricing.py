"""Pricing engine. Pure functions over Decimal, no database access.

Definitions (per one unit sold):

* purchase_rub      = purchase price × FX rate (RUB per unit of the supplier currency)
* supplier_fee_rub  = (purchase × supplier_fee_pct + supplier_fee_fixed) × FX
* conversion_rub    = (purchase_rub + supplier_fee_rub) × conversion_fee_pct   (foreign currency only)
* full_cost         = purchase_rub + supplier_fee_rub + conversion_rub + other_costs_rub
* sale_rate r       = marketplace% + payment% + refund_reserve% + (1 − marketplace%) × withdrawal%
  (all costs that are a percentage of the sale price P; withdrawal applies to the payout)
* net_profit(P)     = P − full_cost − P × r
* margin(P)         = net_profit / P × 100 %
* roi(P)            = net_profit / full_cost × 100 %

Minimum price — the smallest P that satisfies every guard at once:

* profit ≥ min_profit      →  P ≥ (C + min_profit) / (1 − r)
* margin ≥ min_margin m    →  P ≥ C / (1 − r − m)
* roi ≥ min_roi k          →  P ≥ C × (1 + k) / (1 − r)

and it is rounded *up* to the price step, so rounding never breaks a guard.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from ..shared.money import HUNDRED, ZERO, ceil_to_step, money, pct, to_decimal
from ..shared.timeutil import utcnow

ONE = Decimal(1)


@dataclass(frozen=True)
class PricingPolicy:
    min_profit_rub: Decimal = Decimal("30")
    min_margin_pct: Decimal = Decimal("10")
    min_roi_pct: Decimal = Decimal("10")
    target_profit_rub: Decimal | None = None
    target_margin_pct: Decimal = Decimal("20")
    refund_reserve_pct: Decimal = Decimal("3")
    payment_fee_pct: Decimal = Decimal("0")
    withdrawal_fee_pct: Decimal = Decimal("3")
    conversion_fee_pct: Decimal = Decimal("3")
    other_costs_rub: Decimal = Decimal("0")
    max_market_deviation_pct: Decimal = Decimal("15")
    max_discount_pct: Decimal = Decimal("10")
    max_price_age_minutes: int = 360
    max_market_age_hours: int = 72
    max_purchase_budget_rub: Decimal = Decimal("0")  # daily budget for automatic purchases, 0 = no automatic purchases
    price_step: Decimal = Decimal("1")
    undercut_rub: Decimal = Decimal("1")

    FIELDS = (
        "min_profit_rub",
        "min_margin_pct",
        "min_roi_pct",
        "target_profit_rub",
        "target_margin_pct",
        "refund_reserve_pct",
        "payment_fee_pct",
        "withdrawal_fee_pct",
        "conversion_fee_pct",
        "other_costs_rub",
        "max_market_deviation_pct",
        "max_discount_pct",
        "max_price_age_minutes",
        "max_market_age_hours",
        "max_purchase_budget_rub",
        "price_step",
        "undercut_rub",
    )

    @classmethod
    def from_values(cls, values: dict[str, Any], base: PricingPolicy | None = None) -> PricingPolicy:
        base = base or cls()
        changes: dict[str, Any] = {}
        for key, raw in values.items():
            if key not in cls.FIELDS:
                continue
            if raw is None or raw == "":
                if key == "target_profit_rub":
                    changes[key] = None
                continue
            if key in ("max_price_age_minutes", "max_market_age_hours"):
                changes[key] = int(raw)
            else:
                changes[key] = to_decimal(raw)
        policy = replace(base, **changes)
        policy.validate()
        return policy

    def validate(self) -> None:
        for name in self.FIELDS:
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name}: значение не может быть отрицательным")
        for name in (
            "min_margin_pct",
            "target_margin_pct",
            "refund_reserve_pct",
            "payment_fee_pct",
            "withdrawal_fee_pct",
            "max_discount_pct",
        ):
            if getattr(self, name) >= HUNDRED:
                raise ValueError(f"{name}: должно быть меньше 100 %")
        if self.max_price_age_minutes < 1:
            raise ValueError("max_price_age_minutes: минимум 1 минута")

    def to_values(self) -> dict[str, Any]:
        return {k: (None if v is None else str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items() if k in self.FIELDS}


@dataclass(frozen=True)
class CostInput:
    purchase_price: Decimal | None
    purchase_currency: str = "RUB"
    fx_rate: Decimal | None = None  # RUB per unit of purchase_currency
    supplier_fee_pct: Decimal = ZERO
    supplier_fee_fixed: Decimal = ZERO  # in purchase currency
    marketplace_commission_pct: Decimal = Decimal("20")
    price_captured_at: datetime | None = None
    fx_date: datetime | None = None
    source: str = ""


@dataclass(frozen=True)
class MarketInput:
    competitor_min: Decimal | None = None
    competitor_median: Decimal | None = None
    offers_count: int | None = None
    observed_at: datetime | None = None


@dataclass
class Breakdown:
    purchase_rub: Decimal
    supplier_fee_rub: Decimal
    conversion_rub: Decimal
    other_costs_rub: Decimal
    full_cost: Decimal
    sale_rate_pct: Decimal


@dataclass
class PriceEvaluation:
    price: Decimal
    marketplace_fee: Decimal
    payment_fee: Decimal
    refund_reserve: Decimal
    withdrawal_fee: Decimal
    sale_costs: Decimal
    gross_profit: Decimal  # price − full cost − marketplace commission
    net_profit: Decimal
    margin_pct: Decimal
    roi_pct: Decimal
    meets_guards: bool
    violations: list[str] = field(default_factory=list)


@dataclass
class PricingResult:
    status: str  # ok | below_min | stale_price | no_cost | no_fx | impossible | market_below_min
    can_sell: bool
    breakdown: Breakdown | None
    min_price: Decimal | None
    target_price: Decimal | None
    recommended_price: Decimal | None
    competitive_price: Decimal | None
    current: PriceEvaluation | None
    recommended: PriceEvaluation | None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        def conv(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, dict):
                return {k: conv(v) for k, v in value.items()}
            if isinstance(value, list):
                return [conv(v) for v in value]
            return value

        return conv(asdict(self))


STATUS_LABELS = {
    "ok": "✅ Цена проходит все ограничения",
    "below_min": "🛑 Цена ниже минимальной",
    "stale_price": "⏳ Цена поставщика устарела",
    "no_cost": "❔ Нет закупочной цены",
    "no_fx": "💱 Нет курса валюты",
    "impossible": "⛔ Комиссии съедают всю маржу",
    "market_below_min": "⚠️ Конкуренты продают дешевле нашей минимальной цены",
    "not_calculated": "— Не рассчитано",
}


def _frac(percent: Decimal) -> Decimal:
    return percent / HUNDRED


def sale_rate(policy: PricingPolicy, marketplace_pct: Decimal) -> Decimal:
    """Share of the sale price that goes to price-dependent costs (fraction, not %)."""
    mp = _frac(marketplace_pct)
    return mp + _frac(policy.payment_fee_pct) + _frac(policy.refund_reserve_pct) + (ONE - mp) * _frac(policy.withdrawal_fee_pct)


def full_cost(cost: CostInput, policy: PricingPolicy) -> Breakdown:
    if cost.purchase_price is None:
        raise ValueError("no purchase price")
    currency = cost.purchase_currency.upper()
    if currency == "RUB":
        fx = ONE
    elif cost.fx_rate is None or cost.fx_rate <= 0:
        raise LookupError(f"no FX rate for {currency}")
    else:
        fx = cost.fx_rate
    purchase_rub = money(cost.purchase_price * fx)
    supplier_fee_rub = money((cost.purchase_price * _frac(cost.supplier_fee_pct) + cost.supplier_fee_fixed) * fx)
    conversion = money((purchase_rub + supplier_fee_rub) * _frac(policy.conversion_fee_pct)) if currency != "RUB" else ZERO
    other = money(policy.other_costs_rub)
    total = purchase_rub + supplier_fee_rub + conversion + other
    return Breakdown(
        purchase_rub=purchase_rub,
        supplier_fee_rub=supplier_fee_rub,
        conversion_rub=conversion,
        other_costs_rub=other,
        full_cost=money(total),
        sale_rate_pct=pct(sale_rate(policy, cost.marketplace_commission_pct) * HUNDRED),
    )


def evaluate(price: Decimal, breakdown: Breakdown, policy: PricingPolicy, marketplace_pct: Decimal) -> PriceEvaluation:
    price = money(price)
    mp_fee = money(price * _frac(marketplace_pct))
    payment = money(price * _frac(policy.payment_fee_pct))
    reserve = money(price * _frac(policy.refund_reserve_pct))
    withdrawal = money((price - mp_fee) * _frac(policy.withdrawal_fee_pct))
    sale_costs = mp_fee + payment + reserve + withdrawal
    net = money(price - breakdown.full_cost - sale_costs)
    gross = money(price - breakdown.full_cost - mp_fee)
    margin = pct(net / price * HUNDRED) if price > 0 else Decimal("-100")
    roi = pct(net / breakdown.full_cost * HUNDRED) if breakdown.full_cost > 0 else ZERO
    violations: list[str] = []
    if net < policy.min_profit_rub:
        violations.append(f"чистая прибыль {net} ₽ < минимума {policy.min_profit_rub} ₽")
    if margin < policy.min_margin_pct:
        violations.append(f"маржинальность {margin} % < минимума {policy.min_margin_pct} %")
    if roi < policy.min_roi_pct:
        violations.append(f"рентабельность {roi} % < минимума {policy.min_roi_pct} %")
    return PriceEvaluation(
        price=price,
        marketplace_fee=mp_fee,
        payment_fee=payment,
        refund_reserve=reserve,
        withdrawal_fee=withdrawal,
        sale_costs=money(sale_costs),
        gross_profit=gross,
        net_profit=net,
        margin_pct=margin,
        roi_pct=roi,
        meets_guards=not violations,
        violations=violations,
    )


def minimum_price(breakdown: Breakdown, policy: PricingPolicy, marketplace_pct: Decimal) -> Decimal | None:
    """Smallest price meeting profit, margin and ROI guards; None when impossible."""
    r = sale_rate(policy, marketplace_pct)
    c = breakdown.full_cost
    keep = ONE - r
    m = _frac(policy.min_margin_pct)
    if keep <= 0 or keep - m <= 0:
        return None
    candidates = [
        (c + policy.min_profit_rub) / keep,
        c / (keep - m),
        c * (ONE + _frac(policy.min_roi_pct)) / keep,
    ]
    price = ceil_to_step(max(candidates), policy.price_step)
    # Per-component rounding of fees can cost a kopeck; step up until every guard holds.
    for _ in range(100):
        if evaluate(price, breakdown, policy, marketplace_pct).meets_guards:
            return price
        price = ceil_to_step(price + (policy.price_step if policy.price_step > 0 else Decimal("0.01")), policy.price_step)
    return None


def target_price(breakdown: Breakdown, policy: PricingPolicy, marketplace_pct: Decimal, min_price: Decimal) -> Decimal:
    r = sale_rate(policy, marketplace_pct)
    keep = ONE - r
    c = breakdown.full_cost
    candidates = [min_price]
    if policy.target_profit_rub is not None:
        candidates.append((c + policy.target_profit_rub) / keep)
    tm = _frac(policy.target_margin_pct)
    if keep - tm > 0:
        candidates.append(c / (keep - tm))
    return ceil_to_step(max(candidates), policy.price_step)


def market_is_fresh(market: MarketInput | None, policy: PricingPolicy, now: datetime | None = None) -> bool:
    if market is None or market.observed_at is None or market.competitor_min is None:
        return False
    now = now or utcnow()
    return now - market.observed_at <= timedelta(hours=policy.max_market_age_hours)


def calculate(
    cost: CostInput,
    policy: PricingPolicy,
    *,
    current_price: Decimal | None = None,
    market: MarketInput | None = None,
    now: datetime | None = None,
) -> PricingResult:
    now = now or utcnow()
    notes: list[str] = []
    mp_pct = cost.marketplace_commission_pct

    def blocked(status: str, note: str) -> PricingResult:
        return PricingResult(status, False, None, None, None, None, None, None, None, [note])

    if cost.purchase_price is None:
        return blocked("no_cost", "Нет закупочной цены: подключите поставщика или укажите себестоимость вручную")
    try:
        breakdown = full_cost(cost, policy)
    except LookupError:
        return blocked("no_fx", f"Нет курса {cost.purchase_currency} к рублю: синхронизируйте курсы ЦБ")

    stale = cost.price_captured_at is None or now - cost.price_captured_at > timedelta(minutes=policy.max_price_age_minutes)
    min_p = minimum_price(breakdown, policy, mp_pct)
    if min_p is None:
        return PricingResult(
            "impossible",
            False,
            breakdown,
            None,
            None,
            None,
            None,
            None,
            None,
            [f"Доля комиссий и резервов {breakdown.sale_rate_pct} % не оставляет места для минимальной маржи {policy.min_margin_pct} %"],
        )
    tgt = target_price(breakdown, policy, mp_pct, min_p)
    recommended = tgt
    competitive: Decimal | None = None
    status = "ok"

    if market_is_fresh(market, policy, now):
        assert market is not None and market.competitor_min is not None
        undercut = ceil_to_step(market.competitor_min - policy.undercut_rub, policy.price_step)
        floor = max(min_p, ceil_to_step(tgt * (ONE - _frac(policy.max_discount_pct)), policy.price_step))
        competitive = max(undercut, floor)
        if market.competitor_median is not None:
            ceiling = market.competitor_median * (ONE + _frac(policy.max_market_deviation_pct))
            if competitive > ceiling:
                notes.append(
                    f"Наша цена выше медианы рынка {market.competitor_median} ₽ более чем на {policy.max_market_deviation_pct} %: продажи маловероятны"
                )
        recommended = competitive
        if market.competitor_min < min_p:
            status = "market_below_min"
            notes.append(
                f"Минимальная цена конкурентов {market.competitor_min} ₽ ниже нашей минимальной {min_p} ₽. Демпинг запрещён: цена не опускается ниже минимума"
            )
        elif undercut < floor:
            notes.append(f"Скидка ограничена: максимум {policy.max_discount_pct} % от целевой цены")
    elif market is not None and market.competitor_min is not None:
        notes.append("Данные о ценах конкурентов устарели — используется целевая цена без позиционирования")

    if stale:
        status = "stale_price"
        notes.append(
            f"Цена поставщика старше {policy.max_price_age_minutes} мин — публикация и изменение цены приостановлены до обновления"
        )

    current_eval = evaluate(current_price, breakdown, policy, mp_pct) if current_price is not None else None
    if current_eval is not None and current_price is not None and current_price < min_p and status not in ("stale_price",):
        status = "below_min"
        notes.append(f"Текущая цена {money(current_price)} ₽ ниже минимальной {min_p} ₽")

    rec_eval = evaluate(recommended, breakdown, policy, mp_pct)
    can_sell = status in ("ok", "market_below_min", "below_min")
    return PricingResult(
        status=status,
        can_sell=can_sell,
        breakdown=breakdown,
        min_price=min_p,
        target_price=tgt,
        recommended_price=recommended,
        competitive_price=competitive,
        current=current_eval,
        recommended=rec_eval,
        notes=notes,
    )


def quick_min_price(full_cost_rub: Decimal, policy: PricingPolicy, marketplace_pct: Decimal) -> Decimal | None:
    """Calculator for the bot: minimum price for an already known full cost."""
    breakdown = Breakdown(full_cost_rub, ZERO, ZERO, ZERO, money(full_cost_rub), pct(sale_rate(policy, marketplace_pct) * HUNDRED))
    return minimum_price(breakdown, policy, marketplace_pct)
