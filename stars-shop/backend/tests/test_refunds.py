from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from starshop.database.enums import AdminRole, DeliveryStatus, OrderStatus, PaymentStatus, PromoKind, PromoUsageStatus
from starshop.database.models import DeliveryTask, Notification, Order, Payment, PromoCode, PromoCodeUsage
from starshop.payments.base import PaymentProviderError
from starshop.payments.demo import DemoPaymentProvider
from starshop.payments.registry import override_provider
from starshop.worker.main import delivery_tick, refund_tick
from tests.conftest import admin_client, create_order, pay_demo


async def _state(session, order_id: str):
    await session.commit()
    o = await session.get(Order, uuid.UUID(order_id), populate_existing=True)
    p = (
        (
            await session.execute(
                select(Payment)
                .where(Payment.order_id == o.id, Payment.status != PaymentStatus.failed)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    return o, p


async def test_refund_before_delivery(client, session, product):
    session.add(PromoCode(code="SAVE10", kind=PromoKind.percent, value=Decimal("10")))
    await session.commit()
    csrf = await admin_client(client, session)
    order = await create_order(client, product.id, promo_code="save10")
    assert order["amounts"]["discount"] == "16.90"
    await pay_demo(client, order["id"])

    r = await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "по просьбе клиента"}, headers=csrf)
    assert r.status_code == 200, r.text
    o, (p,) = await _state(session, order["id"])
    assert o.status == OrderStatus.refund_pending and p.status == PaymentStatus.refund_pending
    task = (await session.execute(select(DeliveryTask))).scalar_one()
    assert task.status == DeliveryStatus.cancelled  # nothing will be delivered now
    await delivery_tick()

    await refund_tick()
    o, (p,) = await _state(session, order["id"])
    assert o.status == OrderStatus.refunded and p.status == PaymentStatus.refunded
    assert p.refund_reference.startswith("demo_refund_")
    usage = (await session.execute(select(PromoCodeUsage).execution_options(populate_existing=True))).scalar_one()
    assert usage.status == PromoUsageStatus.released
    kinds = set((await session.execute(select(Notification.kind))).scalars())
    assert {"refund_requested", "refunded"} <= kinds and "delivered" not in kinds


async def test_refund_of_completed_order_is_owner_only(client, session, product):
    csrf = await admin_client(client, session, AdminRole.manager, telegram_id=900010)
    order = await create_order(client, product.id)
    await pay_demo(client, order["id"])
    await delivery_tick()
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "dispute"}, headers=csrf)
    assert r.status_code == 409 and r.json()["error"]["code"] == "refund_completed_forbidden"
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "dispute", "allow_completed": True}, headers=csrf)
    assert r.status_code == 403


async def test_refund_not_possible_for_unpaid_order(client, session, product):
    csrf = await admin_client(client, session)
    order = await create_order(client, product.id)
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "test"}, headers=csrf)
    assert r.status_code == 409


async def test_refund_provider_failure_is_retried_then_escalated(client, session, product):
    class BrokenRefunds(DemoPaymentProvider):
        async def refund(self, payment, order, user):
            raise PaymentProviderError("provider down", retryable=True)

    from starshop.config import get_settings

    override_provider(BrokenRefunds(get_settings()))
    csrf = await admin_client(client, session)
    order = await create_order(client, product.id)
    await pay_demo(client, order["id"])
    await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "test refund"}, headers=csrf)
    await refund_tick()
    o, (p,) = await _state(session, order["id"])
    assert p.status == PaymentStatus.refund_pending and p.refund_attempts == 1 and p.refund_next_at is not None
    assert o.status == OrderStatus.refund_pending

    # owner confirms a manual refund with a reference
    r = await client.post(
        f"/api/v1/admin/orders/{order['id']}/payments/{p.id}/confirm-refund", json={"reference": "bank-ref-42"}, headers=csrf
    )
    assert r.status_code == 200, r.text
    o, (p,) = await _state(session, order["id"])
    assert o.status == OrderStatus.refunded and p.refund_reference == "bank-ref-42"
