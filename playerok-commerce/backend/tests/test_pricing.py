"""Pricing engine: full cost, minimum price, net profit, commissions, FX, guards."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

import pytest

from autocommerce.services.pricing import (
    CostInput,
    MarketInput,
    PricingPolicy,
    calculate,
    evaluate,
    full_cost,
    minimum_price,
    quick_min_price,
    sale_rate,
)
from autocommerce.shared.money import ceil_to_step, fmt_money, money, to_decimal
from autocommerce.shared.timeutil import utcnow

POLICY = PricingPolicy(
    min_profit_rub=D("50"),
    min_margin_pct=D("10"),
    min_roi_pct=D("5"),
    refund_reserve_pct=D("2"),
    payment_fee_pct=D("0"),
    withdrawal_fee_pct=D("3"),
    conversion_fee_pct=D("2"),
    price_step=D("1"),
)


def cost(price="10", currency="USD", fx="80", mp="10", captured_ago=0, fee_pct="0", fee_fixed="0") -> CostInput:
    return CostInput(
        purchase_price=D(price),
        purchase_currency=currency,
        fx_rate=D(fx) if fx else None,
        supplier_fee_pct=D(fee_pct),
        supplier_fee_fixed=D(fee_fixed),
        marketplace_commission_pct=D(mp),
        price_captured_at=utcnow() - timedelta(minutes=captured_ago),
    )


def test_float_is_rejected_for_money():
    with pytest.raises(TypeError):
        to_decimal(1.5)  # type: ignore[arg-type]
    assert money("10,555") == D("10.56")
    assert fmt_money(D("1234.5")) == "1 234,50 ₽"


def test_full_cost_includes_supplier_fee_and_conversion():
    br = full_cost(cost(price="10", fee_pct="5", fee_fixed="1"), POLICY)
    # purchase 10 USD × 80 = 800; fee (0.5 + 1) USD × 80 = 120; conversion 2 % of 920 = 18.40
    assert br.purchase_rub == D("800.00")
    assert br.supplier_fee_rub == D("120.00")
    assert br.conversion_rub == D("18.40")
    assert br.full_cost == D("938.40")


def test_rub_purchase_has_no_conversion_cost():
    br = full_cost(cost(price="900", currency="RUB", fx=None), POLICY)
    assert br.conversion_rub == D("0") and br.full_cost == D("900.00")


def test_net_profit_formula():
    br = full_cost(cost(price="900", currency="RUB", fx=None), POLICY)
    ev = evaluate(D("1200"), br, POLICY, D("10"))
    # fee 120, reserve 24, withdrawal 3 % of (1200-120)=32.40 -> costs 176.40
    assert ev.marketplace_fee == D("120.00")
    assert ev.refund_reserve == D("24.00")
    assert ev.withdrawal_fee == D("32.40")
    assert ev.net_profit == D("1200") - D("900") - D("176.40")
    assert ev.gross_profit == D("180.00")
    assert ev.margin_pct == (ev.net_profit / D("1200") * 100).quantize(D("0.0001"))
    assert ev.roi_pct == (ev.net_profit / D("900") * 100).quantize(D("0.0001"))


@pytest.mark.parametrize("purchase", ["10", "99.99", "900", "4321.17"])
@pytest.mark.parametrize("mp", ["0", "10", "20"])
def test_minimum_price_meets_every_guard_and_is_minimal(purchase, mp):
    br = full_cost(cost(price=purchase, currency="RUB", fx=None), POLICY)
    p = minimum_price(br, POLICY, D(mp))
    assert p is not None
    ev = evaluate(p, br, POLICY, D(mp))
    assert ev.meets_guards, ev.violations
    assert ev.net_profit >= POLICY.min_profit_rub
    assert ev.margin_pct >= POLICY.min_margin_pct
    below = evaluate(p - D("1"), br, POLICY, D(mp))
    assert not below.meets_guards  # one step cheaper breaks a guard: the minimum is tight


def test_commission_change_raises_minimum_price():
    br = full_cost(cost(price="1000", currency="RUB", fx=None), POLICY)
    assert minimum_price(br, POLICY, D("20")) > minimum_price(br, POLICY, D("10"))


def test_fx_change_moves_cost_and_minimum():
    low = calculate(cost(fx="80"), POLICY)
    high = calculate(cost(fx="95"), POLICY)
    assert high.breakdown.full_cost > low.breakdown.full_cost
    assert high.min_price > low.min_price


def test_missing_fx_blocks_sale():
    r = calculate(cost(fx=None), POLICY)
    assert r.status == "no_fx" and not r.can_sell


def test_missing_cost_blocks_sale():
    r = calculate(CostInput(purchase_price=None), POLICY)
    assert r.status == "no_cost" and not r.can_sell


def test_stale_supplier_price_blocks_sale():
    r = calculate(cost(captured_ago=POLICY.max_price_age_minutes + 1), POLICY)
    assert r.status == "stale_price" and not r.can_sell
    assert any("устарел" in n or "старше" in n for n in r.notes)


def test_impossible_when_fees_eat_margin():
    greedy = PricingPolicy(min_margin_pct=D("60"), refund_reserve_pct=D("20"))
    r = calculate(cost(mp="25"), greedy)
    assert r.status == "impossible" and r.min_price is None and not r.can_sell


def test_current_price_below_minimum_is_flagged():
    r = calculate(cost(), POLICY, current_price=D("500"))
    assert r.status == "below_min"
    assert r.current is not None and not r.current.meets_guards


def test_no_dumping_below_minimum_when_market_is_cheaper():
    base = calculate(cost(), POLICY)
    market = MarketInput(competitor_min=base.min_price - D("200"), competitor_median=base.min_price, offers_count=10, observed_at=utcnow())
    r = calculate(cost(), POLICY, market=market)
    assert r.status == "market_below_min"
    assert r.recommended_price >= r.min_price


def test_undercut_competitor_within_discount_limit():
    base = calculate(cost(), POLICY)
    market = MarketInput(
        competitor_min=base.target_price + D("300"), competitor_median=base.target_price + D("350"), offers_count=5, observed_at=utcnow()
    )
    r = calculate(cost(), POLICY, market=market)
    assert r.recommended_price == ceil_to_step(market.competitor_min - POLICY.undercut_rub, POLICY.price_step)
    deep = MarketInput(competitor_min=base.min_price + D("1"), competitor_median=None, offers_count=5, observed_at=utcnow())
    r2 = calculate(cost(), POLICY, market=deep)
    floor = ceil_to_step(r2.target_price * (1 - POLICY.max_discount_pct / 100), POLICY.price_step)
    assert r2.recommended_price >= max(r2.min_price, floor)


def test_stale_market_data_is_ignored():
    old = MarketInput(competitor_min=D("100"), observed_at=utcnow() - timedelta(hours=POLICY.max_market_age_hours + 1))
    r = calculate(cost(), POLICY, market=old)
    assert r.competitive_price is None
    assert r.recommended_price == r.target_price


def test_sale_rate_and_quick_calculator():
    assert sale_rate(POLICY, D("10")) == D("0.10") + D("0.02") + D("0.9") * D("0.03")
    assert quick_min_price(D("1000"), POLICY, D("10")) == minimum_price(
        full_cost(cost(price="1000", currency="RUB", fx=None), POLICY), POLICY, D("10")
    )


def test_policy_validation():
    with pytest.raises(ValueError):
        PricingPolicy.from_values({"min_margin_pct": "150"})
    with pytest.raises(ValueError):
        PricingPolicy.from_values({"min_profit_rub": "-1"})
    p = PricingPolicy.from_values({"min_profit_rub": "100", "target_profit_rub": ""})
    assert p.min_profit_rub == D("100") and p.target_profit_rub is None
