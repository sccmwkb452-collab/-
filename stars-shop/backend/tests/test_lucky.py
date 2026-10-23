from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import func, select

from starshop.database.enums import DeliveryStatus, OrderKind, OrderStatus
from starshop.database.models import DeliveryTask, LuckyDraw, Notification, Order, Payment
from starshop.payments.demo import SIGNATURE_HEADER
from starshop.payments.registry import get_payment_provider
from starshop.services import lucky
from starshop.shared.timeutil import utcnow
from starshop.worker.main import delivery_tick, expiry_tick
from tests.conftest import admin_client, create_order, set_runtime, tma

LUCKY_25 = {"lucky": {"chance": 25}}


async def _state(session, order_id: str) -> tuple[Order, LuckyDraw]:
    await session.commit()  # end the snapshot to see what the app committed
    order = await session.get(Order, uuid.UUID(order_id), populate_existing=True)
    draw = await session.get(LuckyDraw, uuid.UUID(order_id), populate_existing=True)
    return order, draw


def _seed_for(draw: LuckyDraw, number: str, *, win: bool) -> str:
    """A client seed that makes this order win (or lose): lets tests pick the outcome."""
    while True:
        seed = secrets.token_hex(8)
        if (lucky.roll(draw.server_seed, seed, number) < draw.chance_bp) == win:
            return seed


async def _pay(client, session, order: dict, *, win: bool) -> dict:
    _, draw = await _state(session, order["id"])
    seed = _seed_for(draw, order["number"], win=win)
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo", "client_seed": seed}, headers=tma())
    assert r.status_code == 200, r.text
    payment = r.json()
    r = await client.post(f"/api/v1/demo/payments/{payment['id']}/complete", json={"outcome": "success"}, headers=tma())
    assert r.json()["result"] == "confirmed"
    return payment


def test_roll_matches_the_published_algorithm():
    server_seed = "9b74c9897bac770ffc029102a200c5de" * 2
    # Same vector as shared/src/lucky.test.ts; independently checked with openssl.
    assert lucky.seed_hash(server_seed) == "69d38f75ec1802034ab2ace92e9c726c2a83a2376119fd30bdf2392970570aa5"
    assert lucky.roll(server_seed, "c0ffee-lucky-42", "7KQ2M9XD") == 2987
    digest = hmac.new(server_seed.encode(), b"c0ffee-lucky-42:7KQ2M9XD", hashlib.sha256).hexdigest()
    assert (int(digest[:16], 16) * 10_000) >> 64 == 2987
    assert lucky.roll_str(2987) == "29.87" and lucky.roll_str(500) == "5.00"
    assert lucky.percent_str(2500) == "25" and lucky.percent_str(1000) == "10" and lucky.percent_str(3750) == "37.5"


def test_roll_is_uniform():
    rolls = [lucky.roll(lucky.new_server_seed(), secrets.token_hex(8), "N") for _ in range(20_000)]
    assert min(rolls) >= 0 and max(rolls) <= 9999
    assert abs(sum(rolls) / len(rolls) - 4999.5) < 75
    # Win rate for a 25 % chance stays close to 25 %.
    assert abs(sum(r < 2500 for r in rolls) / len(rolls) - 0.25) < 0.015


async def test_quote_is_proportional_to_the_chance(client, session, product, custom_product):
    body = {"product_id": product.id, "payment_provider": "demo", **LUCKY_25}
    q = (await client.post("/api/v1/orders/quote", json=body, headers=tma())).json()
    assert q["subtotal"] == "42.25" and q["total"] == "42.25"  # 25 % of 169.00
    assert q["lucky"] == {"chance": "25", "chance_bp": 2500, "prize_value": "169.00", "fee_percent": "0"}
    assert q["stars_amount"] == 100

    await set_runtime(session, "lucky", fee_percent="10")
    q = (await client.post("/api/v1/orders/quote", json=body, headers=tma())).json()
    assert q["subtotal"] == "46.48"  # 42.25 + 10 %

    for chance in (4, 81):
        r = await client.post("/api/v1/orders/quote", json={**body, "lucky": {"chance": chance}}, headers=tma())
        assert r.status_code == 422 and r.json()["error"]["code"] == "lucky_chance_out_of_range"
    r = await client.post("/api/v1/orders/quote", json={**body, "product_id": custom_product.id, "stars_amount": 500}, headers=tma())
    assert r.json()["error"]["code"] == "lucky_package_only"


async def test_availability_follows_settings_and_shop_mode(client, session, product):
    boot = (await client.get("/api/v1/bootstrap")).json()
    assert boot["lucky"] == {"available": True, "min_chance": 5, "max_chance": 80, "fee_percent": "0"}

    await set_runtime(session, "shop", mode="production")  # 'demo_only' turns it off in production
    assert (await client.get("/api/v1/bootstrap")).json()["lucky"]["available"] is False
    await set_runtime(session, "shop", mode="demo")
    await set_runtime(session, "lucky", mode="off")
    r = await client.post("/api/v1/orders/quote", json={"product_id": product.id, "payment_provider": "demo", **LUCKY_25}, headers=tma())
    assert r.status_code == 503 and r.json()["error"]["code"] == "lucky_unavailable"
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo", **LUCKY_25},
        headers={**tma(), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code == 503


async def test_lost_attempt_closes_order_and_reveals_a_verifiable_seed(client, session, product):
    order = await create_order(client, product.id, **LUCKY_25)
    assert order["kind"] == "lucky" and order["total"] == "42.25"
    view = order["lucky"]
    assert view["server_seed"] is None and view["client_seed"] is None and view["roll"] is None
    committed_hash = view["server_seed_hash"]

    # The client seed is mandatory for a Lucky Buy payment.
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())
    assert r.status_code == 422 and r.json()["error"]["code"] == "lucky_client_seed_required"

    await _pay(client, session, order, win=False)
    db_order, draw = await _state(session, order["id"])
    assert db_order.status == OrderStatus.lost
    assert db_order.cost_amount == 0 and db_order.completed_at is not None
    assert draw.won is False and draw.roll_bp >= 2500
    assert await session.scalar(select(func.count()).select_from(DeliveryTask)) == 0

    detail = (await client.get(f"/api/v1/orders/{order['id']}", headers=tma())).json()
    v = detail["lucky"]
    assert detail["status"] == "lost" and detail["status_label"] == "Не повезло"
    assert hashlib.sha256(v["server_seed"].encode()).hexdigest() == committed_hash == v["server_seed_hash"]
    assert lucky.roll(v["server_seed"], v["client_seed"], v["nonce"]) == v["roll_bp"]
    assert v["nonce"] == order["number"] and v["won"] is False

    texts = (await session.execute(select(Notification.kind, Notification.text))).all()
    lost = [t for k, t in texts if k == "lucky_lost"]
    assert len(lost) == 1 and "не повезло" in lost[0] and "DEMO" in lost[0]
    assert "payment_confirmed" not in {k for k, _ in texts}

    listed = (await client.get("/api/v1/orders?status=completed", headers=tma())).json()["items"]
    assert [o["id"] for o in listed] == [order["id"]]


async def test_won_attempt_is_delivered_like_a_purchase(client, session, product):
    order = await create_order(client, product.id, **LUCKY_25)
    await _pay(client, session, order, win=True)
    db_order, draw = await _state(session, order["id"])
    assert db_order.status == OrderStatus.paid and draw.won is True and draw.roll_bp < 2500
    assert db_order.cost_amount == draw.prize_cost == 120  # 100 Stars × 1.20
    text = (await session.execute(select(Notification.text).where(Notification.kind == "payment_confirmed"))).scalar_one()
    assert "Вам повезло" in text

    await delivery_tick()
    db_order, _ = await _state(session, order["id"])
    task = (await session.execute(select(DeliveryTask))).scalar_one()
    assert db_order.status == OrderStatus.completed and task.status == DeliveryStatus.succeeded
    assert db_order.stars_amount == 100


async def test_client_seed_is_fixed_by_the_first_payment(client, session, product):
    order = await create_order(client, product.id, **LUCKY_25)
    first = await client.post(
        f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo", "client_seed": "first-seed-01"}, headers=tma()
    )
    second = await client.post(
        f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo", "client_seed": "other-seed-02"}, headers=tma()
    )
    assert first.json()["id"] == second.json()["id"]
    _, draw = await _state(session, order["id"])
    assert draw.client_seed == "first-seed-01"
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo", "client_seed": "bad seed!"}, headers=tma())
    assert r.status_code == 200  # ignored: the seed is already fixed


async def _signed_event(session, payment_id: str, event_id: str, amount: str) -> tuple[bytes, dict]:
    payment = await session.get(Payment, uuid.UUID(payment_id))
    body = json.dumps(
        {
            "event_id": event_id,
            "type": "payment.updated",
            "payment": {"id": payment.provider_payment_id, "reference": payment_id, "status": "paid", "amount": amount, "currency": "RUB"},
        }
    ).encode()
    return body, {SIGNATURE_HEADER: get_payment_provider("demo").sign(body)}


async def test_draw_happens_once_and_late_payment_is_drawn(client, session, product):
    order = await create_order(client, product.id, **LUCKY_25)
    _, draw = await _state(session, order["id"])
    seed = _seed_for(draw, order["number"], win=False)
    payment = (
        await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo", "client_seed": seed}, headers=tma())
    ).json()

    # The order expires unpaid; its server seed stays secret.
    db_order, _ = await _state(session, order["id"])
    db_order.expires_at = utcnow() - timedelta(minutes=1)
    await session.commit()
    await expiry_tick()
    detail = (await client.get(f"/api/v1/orders/{order['id']}", headers=tma())).json()
    assert detail["status"] == "cancelled" and detail["lucky"]["server_seed"] is None

    # A late capture confirmed by the provider still gets its draw — once.
    body, headers = await _signed_event(session, payment["id"], "evt_late", "42.25")
    assert (await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)).json()["result"] == "confirmed"
    body2, headers2 = await _signed_event(session, payment["id"], "evt_again", "42.25")
    assert (await client.post("/api/v1/webhooks/payments/demo", content=body2, headers=headers2)).json()["result"] == "already_processed"
    db_order, draw = await _state(session, order["id"])
    assert db_order.status == OrderStatus.lost and draw.drawn_at is not None
    events = (await client.get(f"/api/v1/orders/{order['id']}", headers=tma())).json()["timeline"]
    assert sum(e["type"] == "lucky_lost" for e in events) == 1


async def test_discounts_do_not_apply_and_daily_limit(client, session, product):
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo", "promo_code": "ANY", **LUCKY_25},
        headers={**tma(), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "lucky_no_discounts"

    await set_runtime(session, "lucky", daily_limit=2)
    first = await create_order(client, product.id, **LUCKY_25)
    await create_order(client, product.id, **LUCKY_25)
    body = {"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo", **LUCKY_25}
    r = await client.post("/api/v1/orders", json=body, headers={**tma(), "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 409 and r.json()["error"]["code"] == "lucky_daily_limit"
    # An attempt cancelled before payment does not count.
    await client.post(f"/api/v1/orders/{first['id']}/cancel", headers=tma())
    r = await client.post("/api/v1/orders", json=body, headers={**tma(), "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201
    assert (await session.scalar(select(func.count()).select_from(Order).where(Order.kind == OrderKind.lucky))) == 3


async def test_lost_attempt_refund_is_owner_only_and_stats(client, session, product):
    csrf = await admin_client(client, session)
    order = await create_order(client, product.id, **LUCKY_25)
    await _pay(client, session, order, win=False)

    detail = (await client.get(f"/api/v1/admin/orders/{order['id']}", headers=csrf)).json()
    assert detail["lucky"]["won"] is False and detail["order"]["kind"] == "lucky"
    assert "refund_completed" in detail["actions"] and "refund" not in detail["actions"]
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "просто так"}, headers=csrf)
    assert r.status_code == 409 and r.json()["error"]["code"] == "refund_lost_forbidden"

    data = (await client.get("/api/v1/admin/dashboard?period=day&include_demo=true", headers=csrf)).json()
    assert data["lucky"]["attempts"] == 1 and data["lucky"]["wins"] == 0 and data["lucky"]["turnover"] == "42.25"
    assert data["lucky"]["expected_win_rate"] == 25.0
    assert data["money"]["profit"] == "42.25"  # a lost attempt costs nothing
    assert data["orders"]["completed"] == 0

    listed = (await client.get("/api/v1/admin/orders?kind=lucky", headers=csrf)).json()
    assert listed["total"] == 1
    csv = (await client.get("/api/v1/admin/orders/export.csv?kind=lucky", headers=csrf)).text
    assert csv.splitlines()[1].endswith(";lucky;25;no")

    r = await client.post(
        f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "Исключение по обращению", "allow_completed": True}, headers=csrf
    )
    assert r.status_code == 200 and r.json()["order"]["status"] == "refund_pending"
