"""DEMO checkout. Exists only while the shop runs in DEMO mode."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ...database.models import Order, Payment
from ...payments import service as payments
from ...payments.demo import DemoPaymentProvider
from ...payments.registry import get_payment_provider
from ...shared.errors import Conflict, Forbidden, NotFound
from ..deps import RuntimeDep, SessionDep, UserDep, user_rate_limit
from ..schemas import DemoCompleteIn
from ..serializers import order_summary, payment_public

router = APIRouter(prefix="/demo")


async def _owned_demo_payment(session, user, payment_id: uuid.UUID, runtime) -> tuple[Payment, Order]:
    if runtime.shop.mode != "demo":
        raise Forbidden("DEMO-оплата отключена", code="demo_disabled")
    row = (
        await session.execute(
            select(Payment, Order)
            .join(Order, Order.id == Payment.order_id)
            .where(Payment.id == payment_id, Order.user_id == user.id, Payment.provider == "demo")
        )
    ).one_or_none()
    if row is None:
        raise NotFound("Платёж не найден", code="payment_not_found")
    return row[0], row[1]


@router.get("/payments/{payment_id}")
async def demo_payment(payment_id: uuid.UUID, user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    payment, order = await _owned_demo_payment(session, user, payment_id, runtime)
    return {"payment": payment_public(payment), "order": order_summary(order)}


@router.post("/payments/{payment_id}/complete", dependencies=[Depends(user_rate_limit("demo_pay", 10))])
async def complete_demo_payment(
    payment_id: uuid.UUID, body: DemoCompleteIn, user: UserDep, session: SessionDep, runtime: RuntimeDep
) -> dict:
    payment, order = await _owned_demo_payment(session, user, payment_id, runtime)
    if payment.status not in ("created", "pending"):
        raise Conflict("Платёж уже обработан", code="payment_already_processed")
    provider = get_payment_provider("demo")
    assert isinstance(provider, DemoPaymentProvider)
    headers, raw = provider.build_event(payment, body.outcome)
    # Same pipeline as a real provider webhook, including signature check.
    result = await payments.handle_webhook(session, "demo", headers, raw, "demo", runtime)
    await session.commit()
    return {"result": result.get("result"), "order_id": str(order.id)}
