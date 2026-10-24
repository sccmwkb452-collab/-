"""Referral bonuses paid out as Stars."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from starshop.database.enums import OrderKind, OrderStatus
from starshop.database.models import AdminAuditLog, BonusTransaction, Order, Withdrawal
from starshop.services import bonuses
from starshop.worker.main import delivery_tick
from tests.botkit import USER
from tests.conftest import admin_client, get_user, set_runtime, tma


async def give_bonus(client, session, amount: str, telegram_id: int = 100001, username: str = "buyer") -> None:
    await client.get("/api/v1/me", headers=tma(telegram_id, username))
    user = await get_user(session, telegram_id)
    await bonuses.credit(session, user.id, Decimal(amount), kind="referral_reward", dedup_key=f"test:{telegram_id}:{amount}")
    await session.commit()


async def balance(session, telegram_id: int = 100001) -> Decimal:
    session.expire_all()
    return (await get_user(session, telegram_id)).bonus_balance


async def test_request_holds_bonuses_and_checks_limits(client, session, custom_product):
    await give_bonus(client, session, "100.00")
    info = (await client.get("/api/v1/me/withdrawals", headers=tma())).json()
    assert info["enabled"] is True and info["rate"] == "1.6500" and info["available_stars"] == 60 and info["min_stars"] == 50

    too_few = await client.post("/api/v1/me/withdrawals", json={"stars": 10}, headers=tma())
    assert too_few.status_code == 422 and too_few.json()["error"]["code"] == "withdrawal_out_of_range"
    too_many = await client.post("/api/v1/me/withdrawals", json={"stars": 61}, headers=tma())
    assert too_many.status_code == 422 and too_many.json()["error"]["code"] == "insufficient_bonus"

    r = await client.post("/api/v1/me/withdrawals", json={"stars": 60}, headers=tma())
    assert r.status_code == 201 and r.json()["items"][0]["status"] == "pending" and r.json()["items"][0]["amount"] == "99.00"
    assert await balance(session) == Decimal("1.00")
    again = await client.post("/api/v1/me/withdrawals", json={"stars": 50}, headers=tma())
    assert again.status_code in (409, 422)


async def test_approved_payout_is_delivered_as_a_stars_order(client, session, custom_product):
    await give_bonus(client, session, "200.00")
    await client.post("/api/v1/me/withdrawals", json={"stars": 100}, headers=tma())
    w = (await session.execute(select(Withdrawal))).scalar_one()
    wid = w.id
    csrf = await admin_client(client, session)
    listing = (await client.get("/api/v1/admin/withdrawals?status=pending", headers=csrf)).json()
    assert listing["pending"] == 1 and listing["items"][0]["user"]["username"] == "buyer"

    r = await client.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=csrf)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert (await client.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=csrf)).status_code == 409

    await delivery_tick()
    order = (await session.execute(select(Order).execution_options(populate_existing=True))).scalar_one()
    assert order.kind == OrderKind.withdrawal and order.status == OrderStatus.completed
    assert order.stars_amount == 100 and order.total == 0 and order.bonus_spent == Decimal("165.00")
    order_id = order.id
    assert await balance(session) == Decimal("35.00")
    detail = (await client.get(f"/api/v1/admin/orders/{order_id}", headers=csrf)).json()
    assert "refund" not in detail.get("actions", []) and "refund_completed" not in detail.get("actions", [])
    actions = (await session.execute(select(AdminAuditLog.action))).scalars().all()
    assert "withdrawal.approve" in actions


async def test_rejected_payout_returns_bonuses(client, session, custom_product):
    await give_bonus(client, session, "100.00")
    await client.post("/api/v1/me/withdrawals", json={"stars": 50}, headers=tma())
    w = (await session.execute(select(Withdrawal))).scalar_one()
    wid = w.id
    csrf = await admin_client(client, session)
    r = await client.post(f"/api/v1/admin/withdrawals/{wid}/reject", json={"comment": "Подозрительная активность"}, headers=csrf)
    assert r.json()["status"] == "rejected"
    assert await balance(session) == Decimal("100.00")
    kinds = (await session.execute(select(BonusTransaction.kind).order_by(BonusTransaction.id))).scalars().all()
    assert kinds == ["referral_reward", "withdrawal", "withdrawal_return"]


async def test_failed_delivery_gives_bonuses_back(client, session, custom_product):
    await give_bonus(client, session, "100.00", telegram_id=4321, username="demo_fail_user")
    headers = tma(4321, "demo_fail_user")
    await client.post("/api/v1/me/withdrawals", json={"stars": 50}, headers=headers)
    w = (await session.execute(select(Withdrawal))).scalar_one()
    wid = w.id
    csrf = await admin_client(client, session)
    await client.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=csrf)
    early = await client.post(f"/api/v1/admin/withdrawals/{wid}/return", headers=csrf)
    assert early.status_code == 409  # not failed yet
    await delivery_tick()
    order = (await session.execute(select(Order).execution_options(populate_existing=True))).scalar_one()
    assert order.status == OrderStatus.failed
    r = await client.post(f"/api/v1/admin/withdrawals/{wid}/return", headers=csrf)
    assert r.json()["status"] == "returned" and r.json()["order"]["status"] == "refunded"
    assert await balance(session, 4321) == Decimal("100.00")
    assert (await client.post(f"/api/v1/admin/withdrawals/{wid}/return", headers=csrf)).status_code == 409


async def test_auto_approve_and_switch_off(client, session, custom_product):
    await give_bonus(client, session, "100.00")
    await set_runtime(session, "referral", withdrawal_auto_approve=True, withdrawal_rate="2")
    r = await client.post("/api/v1/me/withdrawals", json={"stars": 50}, headers=tma())
    assert r.json()["items"][0]["status"] == "approved" and r.json()["items"][0]["amount"] == "100.00"
    await set_runtime(session, "referral", withdrawal_enabled=False)
    off = await client.post("/api/v1/me/withdrawals", json={"stars": 50}, headers=tma())
    assert off.status_code == 422 and off.json()["error"]["code"] == "withdrawal_disabled"


async def test_withdrawal_in_the_bot(bot_env, session, custom_product):
    calls, send, press = bot_env
    await send("/start")
    user = await get_user(session, USER.id)
    await bonuses.credit(session, user.id, Decimal("90.00"), kind="referral_reward", dedup_key="bot-test")
    await session.commit()
    await send("/ref")
    assert "Доступно к выводу: <b>54 Stars</b>" in calls.texts()[-1]
    await press("ref:withdraw")
    assert "Вывести <b>54 Stars</b> на @anna_buyer?" in calls.texts()[-1]
    await press("ref:withdraw:54")
    assert "Заявка на вывод #" in calls.texts()[-1]
    w = (await session.execute(select(Withdrawal))).scalar_one()
    assert w.stars == 54 and w.status == "pending"
    await press("ref:withdraw:54")  # a second tap: no second request
    assert len((await session.execute(select(Withdrawal))).scalars().all()) == 1
