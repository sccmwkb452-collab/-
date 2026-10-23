from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....config import get_settings
from ....database.enums import ActorType, AdminRole, OrderKind, OrderStatus, PaymentStatus
from ....database.models import DeliveryTask, LuckyDraw, Order, OrderEvent, Payment, PaymentWebhookEvent, User
from ....database.session import get_sessionmaker
from ....delivery import service as delivery_service
from ....payments import service as payments
from ....services import audit, lucky
from ....services.app_settings import load_runtime_settings
from ....services.orders import cancel_order
from ....shared.errors import AppError, NotFound, ValidationFailed
from ....shared.timeutil import fmt_local
from ...deps import ManagerAdmin, OwnerAdmin, RuntimeDep, SessionDep, SupportAdmin
from ...schemas import ReasonIn, ReferenceIn, RefundIn, RetryIn
from ...serializers import event_admin, order_admin, payment_admin, task_admin

router = APIRouter(prefix="/orders")


def _filtered(
    status: str | None, q: str | None, mode: str | None, date_from: datetime | None, date_to: datetime | None, kind: str | None = None
):
    stmt = select(Order, User).join(User, User.id == Order.user_id)
    if kind in OrderKind.__members__:
        stmt = stmt.where(Order.kind == kind)
    if status:
        statuses = [s for s in status.split(",") if s in OrderStatus.__members__]
        if not statuses:
            raise ValidationFailed("Неизвестный статус", code="invalid_status")
        stmt = stmt.where(Order.status.in_(statuses))
    if mode in ("demo", "production"):
        stmt = stmt.where(Order.mode == mode)
    if date_from:
        stmt = stmt.where(Order.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Order.created_at < date_to)
    if q:
        q = q.strip().lstrip("#@")
        conds = [Order.number == q.upper(), User.username.ilike(q), Order.recipient_username.ilike(q)]
        if q.isdigit():
            conds.append(User.telegram_id == int(q))
        try:
            conds.append(Order.id == uuid.UUID(q))
        except ValueError:
            pass
        stmt = stmt.where(or_(*conds))
    return stmt


@router.get("")
async def list_orders(
    ctx: SupportAdmin,
    session: SessionDep,
    status: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    mode: Annotated[str | None, Query(pattern="^(demo|production)$")] = None,
    kind: Annotated[str | None, Query(pattern="^(regular|lucky)$")] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    base = _filtered(status, q, mode, date_from, date_to, kind)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await session.execute(base.order_by(Order.created_at.desc()).limit(limit).offset(offset))).all()
    return {"items": [order_admin(o, u) for o, u in rows], "total": total or 0, "limit": limit, "offset": offset}


async def _load(session: AsyncSession, order_id: uuid.UUID) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFound("Заказ не найден", code="order_not_found")
    return order


async def _detail(session: AsyncSession, order: Order) -> dict:
    user = await session.get(User, order.user_id)
    pays = (await session.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at))).scalars().all()
    events = (await session.execute(select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id))).scalars().all()
    task = (await session.execute(select(DeliveryTask).where(DeliveryTask.order_id == order.id))).scalar_one_or_none()
    draw = await session.get(LuckyDraw, order.id) if order.kind == OrderKind.lucky else None
    hooks = (
        (
            await session.execute(
                select(PaymentWebhookEvent).where(PaymentWebhookEvent.payment_id.in_([p.id for p in pays])).order_by(PaymentWebhookEvent.id)
            )
        )
        .scalars()
        .all()
        if pays
        else []
    )
    return {
        "order": order_admin(order, user),
        "payments": [payment_admin(p) for p in pays],
        "delivery": task_admin(task) if task else None,
        "lucky": lucky.view(draw, order) if draw else None,
        "events": [event_admin(e) for e in events],
        "webhooks": [
            {
                "id": h.id,
                "provider": h.provider,
                "event_id": h.event_id,
                "type": h.event_type,
                "status": h.status,
                "error": h.error,
                "received_at": h.received_at.isoformat(),
            }
            for h in hooks
        ],
        "actions": _actions(order, task, pays),
    }


def _actions(order: Order, task: DeliveryTask | None, pays) -> list[str]:
    actions = []
    if order.status in (OrderStatus.created, OrderStatus.pending_payment):
        actions += ["cancel", "check_payment"]
    if order.status == OrderStatus.cancelled:
        actions.append("check_payment")
    if task is not None and task.status in ("failed", "needs_attention"):
        actions += ["retry_delivery", "confirm_delivery"]
    if (
        task is not None
        and task.status in ("needs_attention", "waiting_provider", "queued")
        and order.status in (OrderStatus.paid, OrderStatus.processing)
    ):
        actions.append("mark_failed")
    if task is not None and task.status == "waiting_provider":
        actions.append("confirm_delivery")
    if order.status in (OrderStatus.paid, OrderStatus.failed):
        actions.append("refund")
    if order.status in (OrderStatus.completed, OrderStatus.lost):
        actions.append("refund_completed")
    if any(p.status == PaymentStatus.refund_pending for p in pays):
        actions.append("confirm_manual_refund")
    return sorted(set(actions))


@router.get("/export.csv")
async def export_csv(
    ctx: ManagerAdmin,
    session: SessionDep,
    status: Annotated[str | None, Query(max_length=200)] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    mode: Annotated[str | None, Query(pattern="^(demo|production)$")] = None,
    kind: Annotated[str | None, Query(pattern="^(regular|lucky)$")] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> StreamingResponse:
    stmt = (
        _filtered(status, q, mode, date_from, date_to, kind)
        .add_columns(LuckyDraw.chance_bp, LuckyDraw.won)
        .outerjoin(LuckyDraw, LuckyDraw.order_id == Order.id)
        .order_by(Order.created_at.desc())
        .limit(50_000)
    )
    await audit.record(
        session,
        ctx.admin,
        "orders.export",
        entity_type="order",
        summary="CSV export",
        after={"status": status, "q": q, "mode": mode, "kind": kind},
        meta=ctx.meta,
    )
    await session.commit()
    tz = get_settings().display_timezone

    def safe(value) -> str:
        # Neutralise spreadsheet formula injection.
        text = "" if value is None else str(value)
        return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text

    async def rows() -> AsyncIterator[str]:
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(
            [
                "number",
                "created_at",
                "paid_at",
                "status",
                "mode",
                "telegram_id",
                "username",
                "stars",
                "recipient",
                "subtotal",
                "discount",
                "bonus",
                "fee",
                "total",
                "cost",
                "currency",
                "payment_provider",
                "delivery_provider",
                "kind",
                "lucky_chance",
                "lucky_won",
            ]
        )
        yield "﻿" + buf.getvalue()
        async with get_sessionmaker()() as s:
            result = await s.stream(stmt)
            async for order, user, chance_bp, won in result:
                buf.seek(0)
                buf.truncate()
                writer.writerow(
                    [
                        safe(v)
                        for v in [
                            order.number,
                            fmt_local(order.created_at, tz),
                            fmt_local(order.paid_at, tz) if order.paid_at else "",
                            order.status,
                            order.mode,
                            user.telegram_id,
                            user.username,
                            order.stars_amount,
                            "self" if order.recipient_type == "self" else order.recipient_username,
                            order.subtotal,
                            order.discount_amount,
                            order.bonus_spent,
                            order.fee_amount,
                            order.total,
                            order.cost_amount or "",
                            order.currency,
                            order.payment_provider,
                            order.delivery_provider,
                            order.kind,
                            lucky.percent_str(chance_bp) if chance_bp else "",
                            "" if won is None else ("yes" if won else "no"),
                        ]
                    ]
                )
                yield buf.getvalue()

    return StreamingResponse(
        rows(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="orders.csv"'}
    )


@router.get("/{order_id}")
async def get_order(order_id: uuid.UUID, ctx: SupportAdmin, session: SessionDep) -> dict:
    return await _detail(session, await _load(session, order_id))


@router.post("/{order_id}/check-payment")
async def check_payment(order_id: uuid.UUID, ctx: SupportAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    """Ask the provider for the real payment status. This is the only way an
    admin can influence 'paid' — and it requires the provider to confirm."""
    order = await _load(session, order_id)
    try:
        result = await payments.reconcile_order(session, order, runtime, source=f"admin:{ctx.admin.id}")
    except AppError as exc:
        result = exc.code
    await audit.record(session, ctx.admin, "order.check_payment", entity_type="order", entity_id=order.id, summary=result, meta=ctx.meta)
    await session.commit()
    return {"result": result, **(await _detail(session, await _load(session, order_id)))}


@router.post("/{order_id}/cancel")
async def cancel(order_id: uuid.UUID, body: ReasonIn, ctx: ManagerAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    order = await _load(session, order_id)
    before = order.status
    await cancel_order(session, order, runtime, actor_type=ActorType.admin, actor_id=ctx.admin.id, reason=body.reason)
    await audit.record(
        session,
        ctx.admin,
        "order.cancel",
        entity_type="order",
        entity_id=order.id,
        summary=body.reason,
        before={"status": before},
        after={"status": "cancelled"},
        meta=ctx.meta,
    )
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/retry-delivery")
async def retry_delivery(order_id: uuid.UUID, body: RetryIn, ctx: ManagerAdmin, session: SessionDep) -> dict:
    order = await _load(session, order_id)
    await delivery_service.retry(session, order, ctx.admin.id, confirm_not_delivered=body.confirm_not_delivered)
    await audit.record(
        session,
        ctx.admin,
        "order.retry_delivery",
        entity_type="order",
        entity_id=order.id,
        after={"confirm_not_delivered": body.confirm_not_delivered},
        meta=ctx.meta,
    )
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/confirm-delivery")
async def confirm_delivery(order_id: uuid.UUID, body: ReferenceIn, ctx: ManagerAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    order = await _load(session, order_id)
    await delivery_service.confirm_manual(session, order, ctx.admin.id, body.reference, runtime)
    await audit.record(
        session,
        ctx.admin,
        "order.confirm_delivery",
        entity_type="order",
        entity_id=order.id,
        summary=body.note,
        after={"reference": body.reference},
        meta=ctx.meta,
    )
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/mark-failed")
async def mark_failed(order_id: uuid.UUID, body: ReasonIn, ctx: ManagerAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    order = await _load(session, order_id)
    await delivery_service.mark_failed(session, order, ctx.admin.id, body.reason, runtime)
    await audit.record(session, ctx.admin, "order.mark_failed", entity_type="order", entity_id=order.id, summary=body.reason, meta=ctx.meta)
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/refund")
async def refund(order_id: uuid.UUID, body: RefundIn, ctx: ManagerAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    order = await _load(session, order_id)
    if body.allow_completed:
        ctx.require(AdminRole.owner)
    before = order.status
    payment = await payments.request_refund(
        session, order, runtime, admin_id=ctx.admin.id, reason=body.reason, allow_completed=body.allow_completed
    )
    await audit.record(
        session,
        ctx.admin,
        "order.refund",
        entity_type="order",
        entity_id=order.id,
        summary=body.reason,
        before={"status": before},
        after={"status": "refund_pending", "payment_id": str(payment.id)},
        meta=ctx.meta,
    )
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/payments/{payment_id}/confirm-refund")
async def confirm_manual_refund(
    order_id: uuid.UUID, payment_id: uuid.UUID, body: ReferenceIn, ctx: OwnerAdmin, session: SessionDep
) -> dict:
    """Records a refund executed outside the provider API (e.g. the automatic
    one failed and the owner returned the money by hand)."""
    order = await _load(session, order_id)
    payment = await session.get(Payment, payment_id)
    if payment is None or payment.order_id != order.id:
        raise NotFound("Платёж не найден", code="payment_not_found")
    runtime = await load_runtime_settings(session)
    await payments.confirm_manual_refund(session, order, payment, body.reference, runtime, ctx.admin.id)
    await audit.record(
        session,
        ctx.admin,
        "payment.confirm_manual_refund",
        entity_type="payment",
        entity_id=payment.id,
        summary=body.note,
        after={"reference": body.reference},
        meta=ctx.meta,
    )
    await session.commit()
    return await _detail(session, order)
