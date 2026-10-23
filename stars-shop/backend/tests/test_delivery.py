from __future__ import annotations

import json
import time
import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from starshop.config import get_settings
from starshop.database.enums import DeliveryStatus, OrderStatus, ShopMode
from starshop.database.models import DeliveryTask, Notification, Order
from starshop.delivery.base import DeliveryError, DeliveryOutcome, DeliveryProvider, DeliveryRequest
from starshop.delivery.demo import DemoDeliveryProvider
from starshop.delivery.http_supplier import HttpSupplierDeliveryProvider, sign
from starshop.delivery.registry import override_provider
from starshop.shared.timeutil import utcnow
from starshop.worker.main import delivery_tick
from tests.conftest import admin_client, create_order, make_admin, pay_demo, tma


class ScriptedProvider(DeliveryProvider):
    """Delivery provider driven by a list of planned results."""

    name = "demo"
    title = "scripted"
    is_demo = True

    def __init__(self, plan: list, idempotent: bool = True):
        self.plan = list(plan)
        self.requests: list[DeliveryRequest] = []
        self.idempotent = idempotent

    async def deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        self.requests.append(request)
        step = self.plan.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


async def paid_order(client, session, product, **kwargs) -> Order:
    order = await create_order(client, product.id, **kwargs)
    await pay_demo(client, order["id"])
    await session.commit()
    return await session.get(Order, uuid.UUID(order["id"]), populate_existing=True)


async def refreshed(session, order: Order) -> tuple[Order, DeliveryTask]:
    await session.commit()
    o = await session.get(Order, order.id, populate_existing=True)
    t = (
        await session.execute(select(DeliveryTask).where(DeliveryTask.order_id == order.id).execution_options(populate_existing=True))
    ).scalar_one()
    return o, t


async def kinds(session) -> list[str]:
    await session.commit()
    return list((await session.execute(select(Notification.kind).order_by(Notification.id))).scalars())


async def test_demo_delivery_completes_and_notifies(client, session, product):
    order = await paid_order(client, session, product)
    assert "delivered" not in await kinds(session)
    await delivery_tick()
    o, t = await refreshed(session, order)
    assert o.status == OrderStatus.completed
    assert t.status == DeliveryStatus.succeeded
    assert t.result["demo"] is True
    k = await kinds(session)
    assert k.index("processing") < k.index("delivered")
    text = (await session.execute(select(Notification.text).where(Notification.kind == "delivered"))).scalar_one()
    assert "DEMO" in text and "не отправлялись" in text
    # nothing left to do: another tick is a no-op
    await delivery_tick()
    assert (await kinds(session)).count("delivered") == 1


async def test_demo_provider_refuses_production_orders():
    with pytest.raises(DeliveryError) as exc:
        await DemoDeliveryProvider().deliver(DeliveryRequest("k", uuid.uuid4(), "N", 100, "x", None, is_demo=False))
    assert exc.value.retryable is False


async def test_retryable_error_is_requeued_with_backoff(client, session, product):
    provider = ScriptedProvider(
        [DeliveryError("busy", retryable=True, definitely_not_executed=True), DeliveryOutcome(status="succeeded", external_id="ext-1")]
    )
    override_provider(provider)
    order = await paid_order(client, session, product)
    await delivery_tick()
    o, t = await refreshed(session, order)
    assert t.status == DeliveryStatus.queued and t.attempts == 1
    assert t.next_attempt_at > utcnow() + timedelta(seconds=20)
    assert o.status == OrderStatus.processing
    t.next_attempt_at = utcnow()
    await session.commit()
    await delivery_tick()
    o, t = await refreshed(session, order)
    assert o.status == OrderStatus.completed and t.attempts == 2
    # the same idempotency key is used for every attempt
    assert len({r.idempotency_key for r in provider.requests}) == 1


async def test_ambiguous_error_without_idempotency_needs_a_human(client, session, product):
    await make_admin(session)
    override_provider(ScriptedProvider([DeliveryError("timeout", retryable=True)], idempotent=False))
    order = await paid_order(client, session, product)
    await delivery_tick()
    o, t = await refreshed(session, order)
    assert t.status == DeliveryStatus.needs_attention
    assert o.status == OrderStatus.processing
    assert "admin_attention" in await kinds(session)
    assert "delivered" not in await kinds(session)


async def test_permanent_error_fails_order(client, session, product):
    await make_admin(session)
    override_provider(ScriptedProvider([DeliveryError("recipient not found", retryable=False)]))
    order = await paid_order(client, session, product)
    await delivery_tick()
    o, t = await refreshed(session, order)
    assert o.status == OrderStatus.failed and t.status == DeliveryStatus.failed
    assert o.failure_reason == "recipient not found"
    k = await kinds(session)
    assert "problem" in k and "admin_attention" in k and "delivered" not in k


async def test_max_attempts(client, session, product):
    err = DeliveryError("busy", retryable=True, definitely_not_executed=True)
    override_provider(ScriptedProvider([err, err]))
    order = await paid_order(client, session, product)
    t = (await refreshed(session, order))[1]
    t.max_attempts = 2
    await session.commit()
    for _ in range(2):
        await delivery_tick()
        o, t = await refreshed(session, order)
        t.next_attempt_at = utcnow()
        await session.commit()
    o, t = await refreshed(session, order)
    assert o.status == OrderStatus.failed and t.attempts == 2


async def test_manual_delivery_and_admin_confirmation(client, session, product, settings, monkeypatch):
    monkeypatch.setattr(settings, "delivery_provider", "manual")
    csrf = await admin_client(client, session)
    order = await paid_order(client, session, product)
    await delivery_tick()
    o, t = await refreshed(session, order)
    assert t.status == DeliveryStatus.needs_attention and o.status == OrderStatus.processing
    assert "delivered" not in await kinds(session)

    r = await client.post(f"/api/v1/admin/orders/{order.id}/confirm-delivery", json={"reference": "x"}, headers=csrf)
    assert r.status_code == 422  # a real reference is mandatory
    r = await client.post(f"/api/v1/admin/orders/{order.id}/confirm-delivery", json={"reference": "fragment-tx-0xabc123"}, headers=csrf)
    assert r.status_code == 200, r.text
    o, t = await refreshed(session, order)
    assert o.status == OrderStatus.completed
    assert t.result["manual_reference"] == "fragment-tx-0xabc123"
    assert "delivered" in await kinds(session)
    audit = (await client.get("/api/v1/admin/audit?action=order.confirm_delivery", headers=csrf)).json()
    assert audit["total"] == 1


async def test_retry_requires_confirmation_for_non_idempotent_provider(client, session, product, settings, monkeypatch):
    monkeypatch.setattr(settings, "delivery_provider", "manual")
    csrf = await admin_client(client, session)
    order = await paid_order(client, session, product)
    await delivery_tick()
    r = await client.post(f"/api/v1/admin/orders/{order.id}/retry-delivery", json={}, headers=csrf)
    assert r.status_code == 422 and r.json()["error"]["code"] == "confirm_not_delivered_required"
    r = await client.post(f"/api/v1/admin/orders/{order.id}/retry-delivery", json={"confirm_not_delivered": True}, headers=csrf)
    assert r.status_code == 200
    _, t = await refreshed(session, order)
    assert t.status == DeliveryStatus.queued


async def test_stale_in_progress_task_recovery(client, session, product):
    order = await paid_order(client, session, product)
    _, t = await refreshed(session, order)
    t.status = DeliveryStatus.in_progress
    t.locked_at = utcnow() - timedelta(hours=1)
    t.next_attempt_at = utcnow() + timedelta(hours=1)
    await session.commit()
    from starshop.database.session import session_scope
    from starshop.delivery.service import recover_stale

    async with session_scope() as s:
        assert await recover_stale(s) == 1
    _, t = await refreshed(session, order)
    assert t.status == DeliveryStatus.queued  # demo provider is idempotent


class FakeSupplier:
    def __init__(self, status: str = "processing"):
        self.status = status
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"id": "sup-1", "status": self.status})
        return httpx.Response(200, json={"id": "sup-1", "status": "completed", "tx_id": "tx-9"})


async def test_http_supplier_contract(client, session, product, settings, monkeypatch):
    monkeypatch.setattr(settings, "delivery_provider", "http_supplier")
    monkeypatch.setattr(settings, "supplier_api_url", "https://supplier.test")
    monkeypatch.setattr(settings, "supplier_api_key", type(settings.supplier_api_key)("key-123"))
    monkeypatch.setattr(settings, "supplier_api_secret", type(settings.supplier_api_secret)("sec-456"))
    fake = FakeSupplier()
    provider = HttpSupplierDeliveryProvider(get_settings(), transport=httpx.MockTransport(fake.handler))
    provider.min_stars, provider.max_stars = 50, 1_000_000
    override_provider(provider)
    await set_production(session)

    order = await paid_order_production(client, session, product)
    await delivery_tick()
    req = fake.requests[0]
    assert req.headers["authorization"] == "Bearer key-123"
    assert req.headers["idempotency-key"] == f"dlv-{order.id}"
    assert req.headers["x-signature"] == sign("sec-456", req.headers["x-timestamp"], req.content)
    body = json.loads(req.content)
    assert body["stars"] == 100 and body["recipient"]["username"] == "buyer"
    o, t = await refreshed(session, order)
    assert t.status == DeliveryStatus.waiting_provider and t.external_id == "sup-1"

    # signed callback completes the order; a forged one is refused
    cb = json.dumps({"id": "sup-1", "status": "completed", "tx_id": "tx-9"}).encode()
    ts = str(int(time.time()))
    forged = await client.post("/api/v1/webhooks/delivery/http_supplier", content=cb, headers={"X-Timestamp": ts, "X-Signature": "00"})
    assert forged.status_code == 401
    ok = await client.post(
        "/api/v1/webhooks/delivery/http_supplier", content=cb, headers={"X-Timestamp": ts, "X-Signature": sign("sec-456", ts, cb)}
    )
    assert ok.json()["result"] == "succeeded"
    o, t = await refreshed(session, order)
    assert o.status == OrderStatus.completed and t.result["tx_id"] == "tx-9"


async def set_production(session):
    from tests.conftest import set_runtime

    await set_runtime(session, "shop", mode="production")


async def paid_order_production(client, session, product) -> Order:
    """Production orders cannot use the DEMO payment provider, so the payment
    is confirmed through a mocked Crypto Pay."""
    from tests.test_cryptopay import FakeCryptoPay, install

    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, provider="cryptopay")
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    fake.pay(next(iter(fake.invoices)))
    r = await client.post(f"/api/v1/orders/{order['id']}/check-payment", headers=tma())
    assert r.json()["result"] == "confirmed"
    await session.commit()
    o = await session.get(Order, uuid.UUID(order["id"]), populate_existing=True)
    assert o.mode == ShopMode.production
    return o
