from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select

from ...database.enums import ActorType, OrderKind, RecipientType
from ...database.models import DeliveryTask, LuckyDraw, OrderEvent, Payment
from ...payments import service as payments
from ...payments.base import PaymentProviderError
from ...payments.registry import get_payment_provider
from ...services import lucky, pricing
from ...services import orders as order_service
from ...services.orders import OrderInput, RecipientInput
from ...shared.errors import AppError, ValidationFailed
from ..deps import RuntimeDep, SessionDep, UserDep, user_rate_limit
from ..schemas import OrderIn, PaymentIn, QuoteIn, RecipientCheckIn
from ..serializers import order_detail, order_summary, payment_public

router = APIRouter()


async def _detail(session, order) -> dict:
    payments_ = (await session.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at))).scalars().all()
    events = (await session.execute(select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id))).scalars().all()
    task = (await session.execute(select(DeliveryTask).where(DeliveryTask.order_id == order.id))).scalar_one_or_none()
    draw = await session.get(LuckyDraw, order.id) if order.kind == OrderKind.lucky else None
    return order_detail(order, payments=list(payments_), events=list(events), task=task, lucky=draw)


@router.post("/orders/quote", dependencies=[Depends(user_rate_limit("quote", 60))])
async def quote(body: QuoteIn, user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    """Live price preview for the checkout screen. Nothing is reserved."""
    delivery = order_service.active_delivery_provider(runtime)
    order_service.check_payment_provider(body.payment_provider, runtime)
    product = await pricing.load_product(session, body.product_id)
    if body.lucky is not None:
        lucky.ensure_available(runtime)
        lq = pricing.build_lucky_quote(
            product=product, chance_percent=body.lucky.chance, payment_provider=body.payment_provider, delivery=delivery, runtime=runtime
        )
        return {
            "product_id": product.id,
            "stars_amount": lq.stars_amount,
            "unit_price": str(lq.unit_price),
            "subtotal": str(lq.subtotal),
            "discount": "0.00",
            "bonus_spent": "0.00",
            "bonus_available": "0.00",
            "fee": str(lq.fee),
            "total": str(lq.total),
            "currency": lq.currency,
            "promo": None,
            "lucky": {
                "chance": lucky.percent_str(lq.chance_bp),
                "chance_bp": lq.chance_bp,
                "prize_value": str(lq.prize_value),
                "fee_percent": str(runtime.lucky.fee_percent),
            },
        }
    q = await pricing.build_quote(
        session,
        user=user,
        product=product,
        stars_requested=body.stars_amount,
        promo_code=body.promo_code,
        use_bonus=body.use_bonus,
        payment_provider=body.payment_provider,
        delivery=delivery,
        runtime=runtime,
        strict_promo=False,
    )
    return {
        "product_id": product.id,
        "stars_amount": q.stars_amount,
        "unit_price": str(q.unit_price),
        "subtotal": str(q.subtotal),
        "discount": str(q.discount),
        "bonus_spent": str(q.bonus_spent),
        "bonus_available": str(q.bonus_available),
        "fee": str(q.fee),
        "total": str(q.total),
        "currency": q.currency,
        "promo": (
            {"code": q.promo.code, "valid": True}
            if q.promo
            else (
                {"code": body.promo_code, "valid": False, "error": q.promo_error["code"], "message": q.promo_error["message"]}
                if q.promo_error
                else None
            )
        ),
    }


@router.post("/recipients/check", dependencies=[Depends(user_rate_limit("recipient", 20))])
async def check_recipient(body: RecipientCheckIn, user: UserDep, runtime: RuntimeDep) -> dict:
    delivery = order_service.active_delivery_provider(runtime)
    rtype, username, _, name = await order_service.resolve_recipient(
        user, RecipientInput(type=RecipientType.username, username=body.username), delivery, runtime, check_remote=True
    )
    return {"ok": True, "username": username, "display_name": name, "is_self": rtype == RecipientType.self}


@router.post("/orders", status_code=201, dependencies=[Depends(user_rate_limit("order_create", 10))])
async def create_order(
    body: OrderIn,
    user: UserDep,
    session: SessionDep,
    runtime: RuntimeDep,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    if not idempotency_key:
        raise ValidationFailed("Не передан заголовок Idempotency-Key", code="idempotency_key_required")
    data = OrderInput(
        product_id=body.product_id,
        stars_amount=body.stars_amount,
        recipient=RecipientInput(type=RecipientType(body.recipient.type), username=body.recipient.username),
        payment_provider=body.payment_provider,
        promo_code=body.promo_code,
        use_bonus=body.use_bonus,
        lucky_chance=body.lucky.chance if body.lucky else None,
    )
    order, created = await order_service.create_order(session, user, data, idempotency_key, runtime)
    await session.commit()
    if not created:
        response.status_code = 200
    return await _detail(session, order)


@router.get("/orders")
async def list_orders(
    user: UserDep,
    session: SessionDep,
    status: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> dict:
    rows, total = await order_service.list_user_orders(session, user, group=status, limit=limit, offset=offset)
    return {"items": [order_summary(o) for o in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/orders/{order_id}")
async def get_order(order_id: uuid.UUID, user: UserDep, session: SessionDep) -> dict:
    order = await order_service.get_user_order(session, user, order_id)
    return await _detail(session, order)


@router.post("/orders/{order_id}/payment", dependencies=[Depends(user_rate_limit("payment_create", 10))])
async def create_payment(order_id: uuid.UUID, body: PaymentIn, user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    order = await order_service.get_user_order(session, user, order_id)
    order_service.ensure_shop_open(runtime)
    try:
        payment = await payments.create_payment(session, order, body.provider, runtime, client_seed=body.client_seed)
    except PaymentProviderError:
        await session.commit()  # keep the failed attempt in the order log
        raise
    await session.commit()
    return payment_public(payment)


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(user_rate_limit("order_cancel", 10))])
async def cancel(order_id: uuid.UUID, user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    order = await order_service.get_user_order(session, user, order_id)
    stale = await order_service.cancel_order(
        session, order, runtime, actor_type=ActorType.user, actor_id=user.telegram_id, reason="Отменён покупателем"
    )
    await session.commit()
    for payment in stale:
        try:
            await get_payment_provider(payment.provider).cancel(payment)
        except Exception:  # best effort, never fail the request
            pass
    return await _detail(session, order)


@router.post("/orders/{order_id}/check-payment", dependencies=[Depends(user_rate_limit("payment_check", 6))])
async def check_payment(order_id: uuid.UUID, user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    """ "I have paid" button: the server asks the provider directly. The
    client's word is never taken as proof of payment."""
    order = await order_service.get_user_order(session, user, order_id)
    result = "skipped"
    if order.status in ("created", "pending_payment", "cancelled"):
        try:
            result = await payments.reconcile_order(session, order, runtime, source="user_check")
        except AppError as exc:
            result = exc.code
        await session.commit()
    await session.refresh(order)
    return {"result": result, "order": await _detail(session, order)}
