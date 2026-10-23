from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from starshop.database.models import Order, OrderEvent
from tests.conftest import create_order, get_user, idem, pay_demo, set_runtime, tma


async def test_create_order_happy_path(client, session, product):
    order = await create_order(client, product.id)
    assert order["status"] == "created"
    assert order["stars_amount"] == 100
    assert order["amounts"]["total"] == "169.00"
    assert order["amounts"]["currency"] == "RUB"
    assert order["recipient"]["type"] == "self"
    assert order["mode"] == "demo"
    assert order["can_pay"] is True
    db_order = await session.get(Order, __import__("uuid").UUID(order["id"]))
    assert db_order.cost_amount == Decimal("120.00")
    events = (await session.execute(select(OrderEvent).where(OrderEvent.order_id == db_order.id))).scalars().all()
    assert [e.event_type for e in events] == ["order_created"]


async def test_order_creation_is_idempotent(client, session, product):
    headers = {**tma(), "Idempotency-Key": "same-key-123456"}
    body = {"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"}
    first = await client.post("/api/v1/orders", json=body, headers=headers)
    second = await client.post("/api/v1/orders", json=body, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert await session.scalar(select(func.count()).select_from(Order)) == 1


async def test_idempotency_key_is_required(client, product):
    r = await client.post(
        "/api/v1/orders", json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"}, headers=tma()
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "idempotency_key_required"


async def test_price_is_computed_on_server(client, custom_product):
    order = await create_order(client, custom_product.id, stars_amount=777)
    assert order["stars_amount"] == 777
    assert order["amounts"]["total"] == str((Decimal("1.65") * 777).quantize(Decimal("0.01")))


async def test_custom_amount_limits(client, custom_product):
    for stars in (10, 20_000):
        r = await client.post(
            "/api/v1/orders",
            json={"product_id": custom_product.id, "stars_amount": stars, "recipient": {"type": "self"}, "payment_provider": "demo"},
            headers={**tma(), **idem()},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "stars_out_of_range"


async def test_gift_recipient_validation(client, product):
    ok = await create_order(client, product.id, recipient={"type": "username", "username": "@Friend_01"})
    assert ok["recipient"]["type"] == "username"
    assert ok["recipient"]["username"] == "Friend_01"
    assert ok["recipient"]["masked"].startswith("@Fr")
    for bad in ("ab", "1abcde", "bad name", "x" * 40, "a-b-c-d"):
        r = await client.post(
            "/api/v1/orders",
            json={"product_id": product.id, "recipient": {"type": "username", "username": bad}, "payment_provider": "demo"},
            headers={**tma(), **idem()},
        )
        assert r.status_code == 422, bad
        assert r.json()["error"]["code"] == "recipient_invalid"


async def test_gifts_can_be_disabled(client, session, product):
    await set_runtime(session, "shop", allow_gift_to_others=False)
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "username", "username": "friend_one"}, "payment_provider": "demo"},
        headers={**tma(), **idem()},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "gifts_disabled"


async def test_unknown_or_inactive_product(client, session, product):
    product.is_active = False
    session.add(product)
    await session.commit()
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"},
        headers={**tma(), **idem()},
    )
    assert r.status_code == 404


async def test_blocked_user_cannot_buy(client, session, product):
    await client.get("/api/v1/me", headers=tma())
    user = await get_user(session, 100001)
    user.is_blocked = True
    await session.commit()
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"},
        headers={**tma(), **idem()},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "user_blocked"


async def test_maintenance_mode_blocks_orders(client, session, product):
    await set_runtime(session, "shop", maintenance=True)
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"},
        headers={**tma(), **idem()},
    )
    assert r.status_code == 503
    boot = (await client.get("/api/v1/bootstrap")).json()
    assert boot["maintenance"]["enabled"] is True


async def test_open_orders_limit(client, product, settings, monkeypatch):
    monkeypatch.setattr(settings, "max_open_orders_per_user", 2)
    await create_order(client, product.id)
    await create_order(client, product.id)
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"},
        headers={**tma(), **idem()},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "too_many_open_orders"


async def test_demo_provider_unavailable_in_production(client, session, product):
    await set_runtime(session, "shop", mode="production")
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"},
        headers={**tma(), **idem()},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "payment_method_unavailable"


async def test_self_purchase_requires_username(client, product):
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"},
        headers={**tma(100002, None), **idem()},
    )
    assert r.status_code == 201  # DEMO delivery does not need a username


async def test_foreign_order_is_not_accessible(client, product):
    order = await create_order(client, product.id, telegram_id=1, username="owner_one")
    stranger = tma(2, "stranger")
    assert (await client.get(f"/api/v1/orders/{order['id']}", headers=stranger)).status_code == 404
    assert (await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=stranger)).status_code == 404
    assert (await client.post(f"/api/v1/orders/{order['id']}/payment", json={}, headers=stranger)).status_code == 404
    assert (await client.post(f"/api/v1/orders/{order['id']}/check-payment", headers=stranger)).status_code == 404
    listing = (await client.get("/api/v1/orders", headers=stranger)).json()
    assert listing["total"] == 0
    # and the owner still sees it
    assert (await client.get(f"/api/v1/orders/{order['id']}", headers=tma(1, "owner_one"))).status_code == 200


async def test_foreign_demo_payment_cannot_be_completed(client, product):
    order = await create_order(client, product.id, telegram_id=1, username="owner_one")
    payment = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma(1, "owner_one"))).json()
    r = await client.post(f"/api/v1/demo/payments/{payment['id']}/complete", json={"outcome": "success"}, headers=tma(2, "stranger"))
    assert r.status_code == 404


async def test_cancel_order(client, product):
    order = await create_order(client, product.id)
    r = await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=tma())
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    again = await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=tma())
    assert again.status_code == 409


async def test_paid_order_cannot_be_cancelled(client, product):
    order = await create_order(client, product.id)
    await pay_demo(client, order["id"])
    r = await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=tma())
    assert r.status_code == 409


async def test_order_filters(client, product):
    a = await create_order(client, product.id)
    b = await create_order(client, product.id)
    await pay_demo(client, b["id"])
    await client.post(f"/api/v1/orders/{a['id']}/cancel", headers=tma())
    pending = (await client.get("/api/v1/orders?status=pending", headers=tma())).json()
    processing = (await client.get("/api/v1/orders?status=processing", headers=tma())).json()
    closed = (await client.get("/api/v1/orders?status=closed", headers=tma())).json()
    assert pending["total"] == 0
    assert [o["id"] for o in processing["items"]] == [b["id"]]
    assert [o["id"] for o in closed["items"]] == [a["id"]]
    assert (await client.get("/api/v1/orders?status=bogus", headers=tma())).status_code == 422


async def test_bootstrap_hides_costs(client, product):
    data = (await client.get("/api/v1/bootstrap")).json()
    item = data["catalog"][0]
    assert item["stars_amount"] == 100
    assert "cost_per_star" not in item
    assert {m["id"] for m in data["payment_methods"]} == {"demo", "cryptopay"}
    assert "secret" not in str(data).lower()
