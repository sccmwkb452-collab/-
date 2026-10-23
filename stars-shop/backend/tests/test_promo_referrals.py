from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from starshop.database.enums import PromoKind, PromoUsageStatus, ReferralStatus
from starshop.database.models import BonusTransaction, PromoCode, PromoCodeUsage, Referral, User
from starshop.shared.timeutil import utcnow
from starshop.worker.main import delivery_tick
from tests.conftest import admin_client, create_order, get_user, idem, set_runtime, tma


async def promo(session, **kw) -> PromoCode:
    p = PromoCode(**{"code": "STAR", "kind": PromoKind.percent, "value": Decimal("10"), **kw})
    session.add(p)
    await session.commit()
    return p


async def quote(client, product_id, code, telegram_id=100001, **kw):
    r = await client.post(
        "/api/v1/orders/quote",
        json={"product_id": product_id, "promo_code": code, "payment_provider": "demo", **kw},
        headers=tma(telegram_id, f"u{telegram_id}"),
    )
    assert r.status_code == 200, r.text
    return r.json()


async def order_with(client, product_id, code, telegram_id=100001):
    return await client.post(
        "/api/v1/orders",
        json={"product_id": product_id, "recipient": {"type": "self"}, "payment_provider": "demo", "promo_code": code},
        headers={**tma(telegram_id, f"u{telegram_id}"), **idem()},
    )


async def test_percent_and_fixed_discounts(client, session, product):
    await promo(session, code="TEN", value=Decimal("10"))
    await promo(session, code="FIX50", kind=PromoKind.fixed, value=Decimal("50"))
    await promo(session, code="CAPPED", value=Decimal("50"), max_discount=Decimal("20"))
    assert (await quote(client, product.id, "ten"))["discount"] == "16.90"
    assert (await quote(client, product.id, "FIX50"))["total"] == "119.00"
    assert (await quote(client, product.id, "capped"))["discount"] == "20.00"


async def test_discount_never_makes_order_free(client, session, product):
    await promo(session, code="ALL", kind=PromoKind.fixed, value=Decimal("10000"))
    q = await quote(client, product.id, "ALL")
    assert Decimal(q["total"]) == Decimal("1.00")


async def test_invalid_promos(client, session, product):
    await promo(session, code="OLD", expires_at=utcnow() - timedelta(days=1))
    await promo(session, code="SOON", starts_at=utcnow() + timedelta(days=1))
    await promo(session, code="OFF", is_active=False)
    await promo(session, code="BIG", min_order_amount=Decimal("1000"))
    expected = {
        "OLD": "promo_expired",
        "SOON": "promo_not_started",
        "OFF": "promo_inactive",
        "BIG": "promo_min_amount",
        "NOPE": "promo_not_found",
    }
    for code, error in expected.items():
        q = await quote(client, product.id, code)
        assert q["promo"]["valid"] is False and q["promo"]["code"] == error, code
        assert q["discount"] == "0.00"
        r = await order_with(client, product.id, code)
        assert r.status_code == 422 and r.json()["error"]["code"] == error


async def test_usage_limits_are_enforced_with_reservations(client, session, product):
    await promo(session, code="ONCE", max_uses=1, per_user_limit=5)
    assert (await order_with(client, product.id, "ONCE", telegram_id=1)).status_code == 201
    r = await order_with(client, product.id, "ONCE", telegram_id=2)
    assert r.json()["error"]["code"] == "promo_exhausted"


async def test_per_user_limit_and_release_on_cancel(client, session, product):
    await promo(session, code="MINE", per_user_limit=1)
    first = (await order_with(client, product.id, "MINE")).json()
    r = await order_with(client, product.id, "MINE")
    assert r.json()["error"]["code"] == "promo_user_limit"
    await client.post(f"/api/v1/orders/{first['id']}/cancel", headers=tma(100001, "u100001"))
    usage = (await session.execute(select(PromoCodeUsage).execution_options(populate_existing=True))).scalar_one()
    assert usage.status == PromoUsageStatus.released
    assert (await order_with(client, product.id, "MINE")).status_code == 201


async def test_first_order_only(client, session, product):
    await promo(session, code="WELCOME", first_order_only=True, per_user_limit=5)
    from tests.conftest import pay_demo

    order = await create_order(client, product.id, telegram_id=7, username="u7")
    await pay_demo(client, order["id"], telegram_id=7, username="u7")
    r = await order_with(client, product.id, "WELCOME", telegram_id=7)
    assert r.json()["error"]["code"] == "promo_first_order_only"


# --- referrals ---------------------------------------------------------------------


async def enable_referrals(session, **kw):
    await set_runtime(session, "referral", enabled=True, reward_kind="percent", reward_value="10", **kw)


async def referrer_code(client, session) -> str:
    await client.get("/api/v1/me", headers=tma(1, "referrer"))
    return (await get_user(session, 1)).referral_code


async def complete_production_order(client, session, product, telegram_id: int, username: str, recipient=None):
    from tests.test_cryptopay import FakeCryptoPay, install
    from tests.test_delivery import set_production

    await set_production(session)
    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, telegram_id=telegram_id, username=username, provider="cryptopay", recipient=recipient)
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma(telegram_id, username))
    fake.pay(next(iter(fake.invoices)))
    await client.post(f"/api/v1/orders/{order['id']}/check-payment", headers=tma(telegram_id, username))
    # production delivery: use the manual provider and confirm as an operator
    return order


async def test_referral_reward_after_completed_production_order(client, session, product, settings, monkeypatch):
    monkeypatch.setattr(settings, "delivery_provider", "manual")
    await enable_referrals(session)
    code = await referrer_code(client, session)
    await client.get("/api/v1/me", headers=tma(2, "invitee", start_param=f"ref_{code}"))
    ref = (await session.execute(select(Referral))).scalar_one()
    assert ref.status == ReferralStatus.pending

    order = await complete_production_order(client, session, product, 2, "invitee")
    csrf = await admin_client(client, session)
    await delivery_tick()
    session.expire_all()
    assert (await session.execute(select(Referral))).scalar_one().status == ReferralStatus.pending  # paid, not delivered yet
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/confirm-delivery", json={"reference": "fragment-123"}, headers=csrf)
    assert r.status_code == 200, r.text
    session.expire_all()
    ref = (await session.execute(select(Referral))).scalar_one()
    assert ref.status == ReferralStatus.rewarded and ref.reward_amount == Decimal("16.90")
    assert (await get_user(session, 1)).bonus_balance == Decimal("16.90")

    # refund reverses the reward exactly once
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "dispute", "allow_completed": True}, headers=csrf)
    assert r.status_code == 200, r.text
    from starshop.worker.main import refund_tick

    await refund_tick()
    await refund_tick()
    session.expire_all()
    assert (await get_user(session, 1)).bonus_balance == Decimal("0.00")
    ledger = (await session.execute(select(BonusTransaction.kind))).scalars().all()
    assert sorted(ledger) == ["referral_reversal", "referral_reward"]


async def test_referral_only_for_new_users(client, session):
    await enable_referrals(session)
    code = await referrer_code(client, session)
    await client.get("/api/v1/me", headers=tma(3, "existing"))
    await client.get("/api/v1/me", headers=tma(3, "existing", start_param=f"ref_{code}"))
    assert (await session.execute(select(Referral))).scalar_one_or_none() is None


async def test_self_referral_is_impossible(client, session):
    await enable_referrals(session)
    await client.get("/api/v1/me", headers=tma(5, "solo", start_param="ref_SOMEONE"))
    user = await get_user(session, 5)
    # replaying your own code later does nothing
    await client.get("/api/v1/me", headers=tma(5, "solo", start_param=f"ref_{user.referral_code}"))
    assert (await session.execute(select(Referral))).scalar_one_or_none() is None


async def test_gift_to_referrer_does_not_pay_reward(client, session, product, settings, monkeypatch):
    monkeypatch.setattr(settings, "delivery_provider", "manual")
    await enable_referrals(session)
    code = await referrer_code(client, session)
    await client.get("/api/v1/me", headers=tma(2, "invitee", start_param=f"ref_{code}"))
    order = await complete_production_order(client, session, product, 2, "invitee", recipient={"type": "username", "username": "referrer"})
    csrf = await admin_client(client, session)
    await delivery_tick()
    await client.post(f"/api/v1/admin/orders/{order['id']}/confirm-delivery", json={"reference": "fragment-777"}, headers=csrf)
    session.expire_all()
    ref = (await session.execute(select(Referral))).scalar_one()
    assert ref.status == ReferralStatus.rejected and ref.reject_reason == "gift_to_referrer"
    assert (await get_user(session, 1)).bonus_balance == Decimal("0.00")


async def test_bonus_spending_is_capped_and_returned_on_cancel(client, session, product):
    await enable_referrals(session, max_bonus_spend_percent="30")
    await client.get("/api/v1/me", headers=tma())
    user = await get_user(session, 100001)
    user.bonus_balance = Decimal("100.00")
    await session.commit()
    order = await create_order(client, product.id, use_bonus=True)
    assert order["amounts"]["bonus_spent"] == "50.70"  # 30% of 169
    assert order["amounts"]["total"] == "118.30"
    session.expire_all()
    assert (await get_user(session, 100001)).bonus_balance == Decimal("49.30")
    await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=tma())
    session.expire_all()
    assert (await get_user(session, 100001)).bonus_balance == Decimal("100.00")
    assert isinstance(uuid.UUID(order["id"]), uuid.UUID)
    assert isinstance(await session.get(User, user.id), User)
