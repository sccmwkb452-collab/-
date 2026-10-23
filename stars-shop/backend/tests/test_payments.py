from __future__ import annotations

import json
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from starshop.database.enums import DeliveryStatus, OrderStatus, PaymentStatus, WebhookStatus
from starshop.database.models import DeliveryTask, Notification, Order, Payment, PaymentWebhookEvent
from starshop.payments.demo import SIGNATURE_HEADER
from starshop.payments.registry import get_payment_provider
from tests.conftest import create_order, make_admin, pay_demo, tma


async def _order(session, order_id: str) -> Order:
    await session.commit()  # end the snapshot to see changes made by the app
    return await session.get(Order, uuid.UUID(order_id), populate_existing=True)


async def test_demo_payment_full_flow(client, session, product):
    order = await create_order(client, product.id)
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())
    payment = r.json()
    assert payment["status"] == "pending"
    assert payment["pay_url"].endswith(f"/pay/demo/{payment['id']}")
    assert payment["pay_url_kind"] == "internal"

    # The same open payment is reused, not duplicated.
    again = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    assert again["id"] == payment["id"]

    db_order = await _order(session, order["id"])
    assert db_order.status == OrderStatus.pending_payment

    r = await client.post(f"/api/v1/demo/payments/{payment['id']}/complete", json={"outcome": "success"}, headers=tma())
    assert r.json()["result"] == "confirmed"

    db_order = await _order(session, order["id"])
    assert db_order.status == OrderStatus.paid
    assert db_order.paid_at is not None
    task = (await session.execute(select(DeliveryTask).where(DeliveryTask.order_id == db_order.id))).scalar_one()
    assert task.status == DeliveryStatus.queued
    kinds = set((await session.execute(select(Notification.kind))).scalars())
    assert {"awaiting_payment", "payment_confirmed"} <= kinds
    assert "delivered" not in kinds


async def test_return_to_app_does_not_mark_paid(client, session, product):
    """Coming back from the payment page (or any client claim) is not proof."""
    order = await create_order(client, product.id)
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())
    r = await client.get(f"/api/v1/orders/{order['id']}?success=true&status=paid", headers=tma())
    assert r.json()["status"] == "pending_payment"
    r = await client.post(f"/api/v1/orders/{order['id']}/check-payment", headers=tma())
    assert r.json()["order"]["status"] == "pending_payment"


async def test_failed_demo_payment_keeps_order_payable(client, session, product):
    order = await create_order(client, product.id)
    await pay_demo(client, order["id"], outcome="fail")
    db_order = await _order(session, order["id"])
    assert db_order.status == OrderStatus.pending_payment
    pays = (await session.execute(select(Payment).where(Payment.order_id == db_order.id))).scalars().all()
    assert [p.status for p in pays] == [PaymentStatus.failed]
    # a new attempt creates a fresh payment
    fresh = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    assert fresh["id"] != str(pays[0].id)


async def test_webhook_with_bad_signature_is_rejected_and_logged(client, session, product):
    order = await create_order(client, product.id)
    payment = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    body = json.dumps(
        {
            "event_id": "evt_forged",
            "type": "payment.updated",
            "payment": {"id": "x", "reference": payment["id"], "status": "paid", "amount": "169.00", "currency": "RUB"},
        }
    ).encode()
    r = await client.post("/api/v1/webhooks/payments/demo", content=body, headers={SIGNATURE_HEADER: "0" * 64})
    assert r.status_code == 401
    events = (await session.execute(select(PaymentWebhookEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].status == WebhookStatus.rejected
    assert events[0].event_id is None  # forged ids cannot pre-claim real ones
    assert (await _order(session, order["id"])).status == OrderStatus.pending_payment


async def _signed_demo_event(
    session,
    payment_id: str,
    *,
    event_id: str,
    amount: str = "169.00",
    currency: str = "RUB",
    status: str = "paid",
    reference: str | None = None,
):
    payment = await session.get(Payment, uuid.UUID(payment_id))
    provider = get_payment_provider("demo")
    body = json.dumps(
        {
            "event_id": event_id,
            "type": "payment.updated",
            "payment": {
                "id": payment.provider_payment_id,
                "reference": reference or payment_id,
                "status": status,
                "amount": amount,
                "currency": currency,
            },
        },
        separators=(",", ":"),
    ).encode()
    return body, {SIGNATURE_HEADER: provider.sign(body)}


async def test_duplicate_webhook_is_processed_once(client, session, product):
    order = await create_order(client, product.id)
    payment = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    body, headers = await _signed_demo_event(session, payment["id"], event_id="evt_1")
    first = await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
    second = await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
    assert first.json() == {"ok": True, "result": "confirmed"}
    assert second.json() == {"ok": True, "duplicate": True}
    # A *different* event for the same payment is also harmless.
    body3, headers3 = await _signed_demo_event(session, payment["id"], event_id="evt_2")
    third = await client.post("/api/v1/webhooks/payments/demo", content=body3, headers=headers3)
    assert third.json()["result"] == "already_processed"
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(DeliveryTask)) == 1
    assert await session.scalar(select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.succeeded)) == 1
    assert await session.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "payment_confirmed")) == 1


async def test_amount_or_currency_mismatch_is_not_accepted(client, session, product):
    await make_admin(session)
    order = await create_order(client, product.id)
    payment = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    for i, (amount, currency) in enumerate([("1.00", "RUB"), ("169.00", "USD")]):
        body, headers = await _signed_demo_event(session, payment["id"], event_id=f"evt_mm{i}", amount=amount, currency=currency)
        r = await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
        assert r.json()["result"] == "amount_mismatch"
    assert (await _order(session, order["id"])).status == OrderStatus.pending_payment
    kinds = set((await session.execute(select(Notification.kind))).scalars())
    assert "admin_attention" in kinds


async def test_reference_mismatch_is_not_accepted(client, session, product):
    order = await create_order(client, product.id)
    payment = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    body, headers = await _signed_demo_event(session, payment["id"], event_id="evt_ref", reference=str(uuid.uuid4()))
    r = await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
    assert r.json()["result"] == "reference_mismatch"
    assert (await _order(session, order["id"])).status == OrderStatus.pending_payment


async def test_second_capture_is_flagged_as_duplicate_and_refunded(client, session, product):
    order = await create_order(client, product.id)
    first = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    # Customer opens another payment method too (simulated by cancelling and creating a second payment row)
    p2 = Payment(
        order_id=uuid.UUID(order["id"]),
        provider="demo",
        provider_payment_id="demo_second",
        idempotency_key=f"{order['id']}:demo:x",
        status=PaymentStatus.pending,
        amount=Decimal("169.00"),
        currency="RUB",
        is_demo=True,
    )
    session.add(p2)
    await session.commit()
    body, headers = await _signed_demo_event(session, first["id"], event_id="evt_a")
    await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
    body2, headers2 = await _signed_demo_event(session, str(p2.id), event_id="evt_b")
    r = await client.post("/api/v1/webhooks/payments/demo", content=body2, headers=headers2)
    assert r.json()["result"] == "duplicate_refund"
    await session.refresh(p2)
    assert p2.status == PaymentStatus.refund_pending and p2.is_duplicate

    from starshop.worker.main import refund_tick

    await refund_tick()
    await session.refresh(p2)
    assert p2.status == PaymentStatus.refunded
    assert (await _order(session, order["id"])).status == OrderStatus.paid  # the order itself is untouched


async def test_late_payment_revives_expired_order(client, session, product):
    order = await create_order(client, product.id)
    payment = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    db_order = await _order(session, order["id"])
    from datetime import timedelta

    from starshop.shared.timeutil import utcnow
    from starshop.worker.main import expiry_tick

    db_order.expires_at = utcnow() - timedelta(minutes=1)
    await session.commit()
    await expiry_tick()
    assert (await _order(session, order["id"])).status == OrderStatus.cancelled
    body, headers = await _signed_demo_event(session, payment["id"], event_id="evt_late")
    r = await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
    assert r.json()["result"] == "confirmed"
    db_order = await _order(session, order["id"])
    assert db_order.status == OrderStatus.paid


async def test_unknown_provider_webhook(client):
    r = await client.post("/api/v1/webhooks/payments/nope", content=b"{}")
    assert r.status_code == 404


async def test_webhook_crash_rolls_back_so_retry_succeeds(client, session, product, monkeypatch):
    order = await create_order(client, product.id)
    payment = (await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())).json()
    body, headers = await _signed_demo_event(session, payment["id"], event_id="evt_crash")

    from starshop.payments import service

    original = service.apply_state

    async def boom(*args, **kwargs):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(service, "apply_state", boom)
    r = await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
    assert r.status_code == 500
    monkeypatch.setattr(service, "apply_state", original)
    r = await client.post("/api/v1/webhooks/payments/demo", content=body, headers=headers)
    assert r.json()["result"] == "confirmed"
    statuses = sorted((await session.execute(select(PaymentWebhookEvent.status))).scalars())
    assert statuses == [WebhookStatus.failed, WebhookStatus.processed]
