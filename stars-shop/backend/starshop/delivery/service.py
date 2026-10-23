"""Delivery task processing.

The worker claims due tasks with ``FOR UPDATE SKIP LOCKED`` (several
workers can run safely), calls the provider outside of any DB lock and then
records the outcome. Retry policy:

* provider error marked *definitely not executed* → retry with backoff;
* ambiguous error (e.g. timeout) → retry only if the provider de-duplicates
  by idempotency key, otherwise park the task for a human (never risk
  delivering twice);
* permanent error → order ``failed`` and admins are alerted.

The "Stars delivered" notification is enqueued in the same transaction that
marks the order completed — i.e. only after the provider confirmed it.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ActorType, DeliveryStatus, OrderStatus, ShopMode
from ..database.models import DeliveryTask, Order
from ..database.session import session_scope
from ..notifications import service as notify
from ..notifications import templates
from ..services import referrals
from ..services.app_settings import RuntimeSettings, load_runtime_settings
from ..services.orders import lock_order
from ..services.state_machine import add_event, transition
from ..shared.errors import Conflict, ValidationFailed
from ..shared.timeutil import utcnow
from .base import DeliveryError, DeliveryOutcome, DeliveryRequest
from .registry import get_delivery_provider

log = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=30)
STALE_AFTER = timedelta(minutes=10)


def _backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** max(attempt - 1, 0), 3600))


def build_request(task: DeliveryTask, order: Order) -> DeliveryRequest:
    return DeliveryRequest(
        idempotency_key=task.idempotency_key,
        order_id=order.id,
        order_number=order.number,
        stars=order.stars_amount,
        recipient_username=order.recipient_username,
        recipient_telegram_id=order.recipient_telegram_id,
        is_demo=order.mode == ShopMode.demo,
    )


async def claim_due(session: AsyncSession, worker_id: str, limit: int = 10) -> list[uuid.UUID]:
    now = utcnow()
    rows = (
        (
            await session.execute(
                select(DeliveryTask)
                .where(
                    DeliveryTask.status.in_((DeliveryStatus.queued, DeliveryStatus.waiting_provider)), DeliveryTask.next_attempt_at <= now
                )
                .order_by(DeliveryTask.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    ids = []
    for task in rows:
        if task.status == DeliveryStatus.queued:
            task.attempts += 1
        task.status = DeliveryStatus.in_progress if task.status == DeliveryStatus.queued else DeliveryStatus.waiting_provider
        task.locked_at = now
        task.locked_by = worker_id
        # Push the poll time forward so a concurrent claimer skips it.
        task.next_attempt_at = now + STALE_AFTER
        ids.append(task.id)
    return ids


async def process_task(task_id: uuid.UUID) -> str:
    # 1) mark the order as processing
    async with session_scope() as session:
        runtime = await load_runtime_settings(session)
        task = await session.get(DeliveryTask, task_id)
        if task is None:
            return "missing"
        order = await lock_order(session, task.order_id)
        if order.status == OrderStatus.paid:
            transition(session, order, OrderStatus.processing, message="Заказ передан на доставку")
            await notify.notify_order(session, order, "processing", templates.processing(order), runtime)
        elif order.status != OrderStatus.processing:
            task.status = DeliveryStatus.cancelled
            task.locked_at = None
            return "order_not_deliverable"
        request = build_request(task, order)
        polling = task.status == DeliveryStatus.waiting_provider and task.external_id
        external_id = task.external_id
        provider = get_delivery_provider(task.provider)
        add_event(
            session,
            order,
            "delivery_attempt",
            public=False,
            data={"attempt": task.attempts, "provider": task.provider, "poll": bool(polling)},
        )

    # 2) call the provider (no DB locks held)
    error: DeliveryError | None = None
    outcome: DeliveryOutcome | None = None
    try:
        outcome = await (provider.check(external_id, request) if polling and external_id else provider.deliver(request))
    except DeliveryError as exc:
        error = exc
    except Exception as exc:  # unexpected bug or library error: treat as ambiguous
        log.exception("delivery provider crashed", extra={"task_id": str(task_id)})
        error = DeliveryError(f"Внутренняя ошибка: {exc.__class__.__name__}", retryable=True)

    # 3) record the result
    async with session_scope() as session:
        runtime = await load_runtime_settings(session)
        task = (await session.execute(select(DeliveryTask).where(DeliveryTask.id == task_id).with_for_update())).scalar_one()
        order = await lock_order(session, task.order_id)
        if task.status not in (DeliveryStatus.in_progress, DeliveryStatus.waiting_provider):
            return "state_changed"  # an admin acted meanwhile
        task.locked_at = None
        task.locked_by = None
        if error is not None:
            return await _handle_error(session, task, order, error, provider.idempotent, runtime)
        assert outcome is not None
        return await _apply_outcome(session, task, order, outcome, runtime)


async def _apply_outcome(
    session: AsyncSession,
    task: DeliveryTask,
    order: Order,
    outcome: DeliveryOutcome,
    runtime: RuntimeSettings,
    *,
    actor_type: ActorType = ActorType.provider,
    actor_id: str | None = None,
) -> str:
    if outcome.external_id:
        task.external_id = outcome.external_id
    task.result = {**(task.result or {}), **outcome.details, "message": outcome.message}
    if outcome.status == "succeeded":
        task.status = DeliveryStatus.succeeded
        task.completed_at = utcnow()
        task.last_error = None
        transition(
            session,
            order,
            OrderStatus.completed,
            actor_type=actor_type,
            actor_id=actor_id or task.provider,
            message="Stars доставлены" if order.mode == ShopMode.production else "DEMO: заказ выполнен без отправки Stars",
            data={"external_id": task.external_id},
        )
        await notify.notify_order(session, order, "delivered", templates.delivered(order), runtime)
        await referrals.on_order_completed(session, order, runtime)
        return "succeeded"
    if outcome.status == "pending":
        task.status = DeliveryStatus.waiting_provider
        task.next_attempt_at = utcnow() + POLL_INTERVAL
        return "pending"
    if outcome.status == "needs_attention":
        task.status = DeliveryStatus.needs_attention
        task.last_error = outcome.message
        add_event(session, order, "delivery_needs_attention", message="Заказ обрабатывается оператором", data={"reason": outcome.message})
        await notify.admin_attention(session, order, outcome.message or "Нужна ручная доставка", runtime, f"manual:{task.attempts}")
        return "needs_attention"
    # failed
    return await _fail(session, task, order, outcome.message or "Поставщик отклонил заказ", runtime)


async def _fail(session: AsyncSession, task: DeliveryTask, order: Order, reason: str, runtime: RuntimeSettings) -> str:
    task.status = DeliveryStatus.failed
    task.last_error = reason
    order.failure_reason = reason
    transition(
        session,
        order,
        OrderStatus.failed,
        actor_type=ActorType.provider,
        actor_id=task.provider,
        message="Доставка не выполнена",
        data={"reason": reason},
    )
    await notify.notify_order(session, order, "problem", templates.problem(order), runtime, dedup_suffix=f":{task.attempts}")
    await notify.admin_attention(session, order, f"Доставка не выполнена: {reason}", runtime, f"failed:{task.attempts}")
    return "failed"


async def _handle_error(
    session: AsyncSession, task: DeliveryTask, order: Order, error: DeliveryError, idempotent: bool, runtime: RuntimeSettings
) -> str:
    task.last_error = error.message
    add_event(
        session,
        order,
        "delivery_error",
        actor_type=ActorType.provider,
        actor_id=task.provider,
        public=False,
        message=error.message,
        data={"retryable": error.retryable, "not_executed": error.definitely_not_executed},
    )
    if not error.retryable:
        return await _fail(session, task, order, error.message, runtime)
    if not (error.definitely_not_executed or idempotent):
        task.status = DeliveryStatus.needs_attention
        await notify.admin_attention(
            session,
            order,
            f"Неясный результат доставки ({error.message}). Проверьте у поставщика перед повтором",
            runtime,
            f"ambiguous:{task.attempts}",
        )
        return "needs_attention"
    if task.attempts >= task.max_attempts:
        return await _fail(session, task, order, f"Превышено число попыток: {error.message}", runtime)
    task.status = DeliveryStatus.queued
    task.next_attempt_at = utcnow() + _backoff(task.attempts)
    return "retry_scheduled"


async def recover_stale(session: AsyncSession) -> int:
    """Tasks left ``in_progress`` by a crashed worker."""
    cutoff = utcnow() - STALE_AFTER
    tasks = (
        (
            await session.execute(
                select(DeliveryTask)
                .where(DeliveryTask.status == DeliveryStatus.in_progress, DeliveryTask.locked_at < cutoff)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    runtime = await load_runtime_settings(session) if tasks else None
    for task in tasks:
        provider = get_delivery_provider(task.provider)
        task.locked_at = None
        task.locked_by = None
        if provider.idempotent:
            task.status = DeliveryStatus.queued
            task.next_attempt_at = utcnow()
        else:
            task.status = DeliveryStatus.needs_attention
            task.last_error = "Обработка прервалась — проверьте, была ли выполнена доставка"
            order = await session.get(Order, task.order_id)
            if order is not None and runtime is not None:
                await notify.admin_attention(session, order, task.last_error, runtime, f"stale:{task.attempts}")
    return len(tasks)


# --- admin actions -----------------------------------------------------------------


async def _task_for(session: AsyncSession, order: Order) -> DeliveryTask:
    task = (await session.execute(select(DeliveryTask).where(DeliveryTask.order_id == order.id).with_for_update())).scalar_one_or_none()
    if task is None:
        raise Conflict("Для заказа нет задачи доставки", code="no_delivery_task")
    return task


async def retry(session: AsyncSession, order: Order, admin_id: int, *, confirm_not_delivered: bool) -> DeliveryTask:
    order = await lock_order(session, order.id)
    task = await _task_for(session, order)
    if task.status not in (DeliveryStatus.failed, DeliveryStatus.needs_attention):
        raise Conflict("Повтор доступен только для неуспешной доставки", code="retry_not_allowed")
    provider = get_delivery_provider(task.provider)
    if not provider.idempotent and task.attempts > 0 and not confirm_not_delivered:
        raise ValidationFailed(
            "Поставщик не защищает от повторной доставки. Подтвердите, что Stars не были зачислены",
            code="confirm_not_delivered_required",
        )
    if order.status == OrderStatus.failed:
        transition(session, order, OrderStatus.processing, actor_type=ActorType.admin, actor_id=admin_id, message="Повторная доставка")
    elif order.status != OrderStatus.processing:
        raise Conflict("Заказ не ожидает доставки", code="retry_not_allowed")
    task.status = DeliveryStatus.queued
    task.next_attempt_at = utcnow()
    task.max_attempts = max(task.max_attempts, task.attempts + 3)
    add_event(session, order, "delivery_retry", actor_type=ActorType.admin, actor_id=admin_id, public=False)
    return task


async def confirm_manual(session: AsyncSession, order: Order, admin_id: int, reference: str, runtime: RuntimeSettings) -> DeliveryTask:
    """Operator confirms that the Stars were delivered outside the system
    (e.g. bought on Fragment). Requires a reference for the audit trail."""
    reference = reference.strip()
    if len(reference) < 4:
        raise ValidationFailed("Укажите идентификатор транзакции или ссылку на подтверждение", code="reference_required")
    order = await lock_order(session, order.id)
    task = await _task_for(session, order)
    if task.status not in (DeliveryStatus.needs_attention, DeliveryStatus.failed, DeliveryStatus.waiting_provider):
        raise Conflict("Подтверждение доступно для заказов, ожидающих ручной обработки", code="confirm_not_allowed")
    if order.status not in (OrderStatus.processing, OrderStatus.failed):
        raise Conflict("Заказ не ожидает доставки", code="confirm_not_allowed")
    outcome = DeliveryOutcome(
        status="succeeded",
        external_id=task.external_id,
        message="Доставка подтверждена оператором",
        details={"manual_reference": reference, "confirmed_by_admin": admin_id},
    )
    await _apply_outcome(session, task, order, outcome, runtime, actor_type=ActorType.admin, actor_id=str(admin_id))
    return task


async def mark_failed(session: AsyncSession, order: Order, admin_id: int, reason: str, runtime: RuntimeSettings) -> None:
    order = await lock_order(session, order.id)
    task = await _task_for(session, order)
    if task.status not in (DeliveryStatus.needs_attention, DeliveryStatus.waiting_provider, DeliveryStatus.queued):
        raise Conflict("Действие недоступно", code="mark_failed_not_allowed")
    if order.status == OrderStatus.paid:
        transition(session, order, OrderStatus.processing, actor_type=ActorType.admin, actor_id=admin_id)
    await _fail(session, task, order, reason or "Отмечено администратором", runtime)


async def handle_callback(session: AsyncSession, provider_name: str, headers: dict[str, str], body: bytes) -> str:
    provider = get_delivery_provider(provider_name)
    callback = provider.parse_callback({k.lower(): v for k, v in headers.items()}, body)
    task = (
        await session.execute(
            select(DeliveryTask)
            .where(DeliveryTask.provider == provider_name, DeliveryTask.external_id == callback.external_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        return "unknown"
    if task.status not in (DeliveryStatus.waiting_provider, DeliveryStatus.in_progress, DeliveryStatus.queued):
        return "already_final"
    order = await lock_order(session, task.order_id)
    runtime = await load_runtime_settings(session)
    if order.status == OrderStatus.paid:
        transition(session, order, OrderStatus.processing)
    return await _apply_outcome(session, task, order, callback.outcome, runtime)
