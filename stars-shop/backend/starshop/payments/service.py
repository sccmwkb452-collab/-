"""Payment orchestration.

Guarantees:
* one open payment per order and provider is reused instead of duplicated;
* webhooks are processed only after signature verification, exactly once
  (``payment_webhook_events`` unique ``(provider, event_id)`` written in the
  same transaction as the effects);
* an order becomes ``paid`` only if the provider-reported amount and
  currency equal the payment's, and the reference matches our payment id;
* a second capture for an already paid order is never "successful" — it is
  flagged as a duplicate and refunded;
* refunds run asynchronously in the worker and are retried with backoff.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import ActorType, DeliveryStatus, OrderKind, OrderStatus, PaymentStatus, WebhookStatus
from ..database.models import DeliveryTask, LuckyDraw, Order, Payment, PaymentWebhookEvent, User
from ..notifications import service as notify
from ..notifications import templates
from ..services import bonuses, lucky, referrals
from ..services import promo as promo_service
from ..services.app_settings import RuntimeSettings
from ..services.orders import check_payment_provider, lock_order, release_reservations
from ..services.state_machine import OPEN_STATUSES, add_event, transition
from ..shared.errors import Conflict, NotFound, Unauthorized, ValidationFailed
from ..shared.items import item_title
from ..shared.masking import scrub
from ..shared.money import ZERO
from ..shared.timeutil import utcnow
from .base import PaymentContext, PaymentProviderError, ProviderPaymentState, WebhookSignatureError
from .registry import get_payment_provider

log = logging.getLogger(__name__)

OPEN_PAYMENT = (PaymentStatus.created, PaymentStatus.pending)


# ---------------------------------------------------------------------------
# Creating payments
# ---------------------------------------------------------------------------


async def create_payment(
    session: AsyncSession,
    order: Order,
    provider_name: str | None,
    runtime: RuntimeSettings,
    *,
    client_seed: str | None = None,
    notify_user: bool = True,
) -> Payment:
    """``notify_user=False`` when the caller (the bot) shows the payment link itself."""
    order = await lock_order(session, order.id)
    if order.status not in OPEN_STATUSES:
        raise Conflict("Заказ уже оплачен или закрыт", code="order_not_payable")
    now = utcnow()
    if order.expires_at and order.expires_at <= now:
        raise Conflict("Время на оплату истекло. Оформите новый заказ", code="order_expired")
    provider_name = provider_name or order.payment_provider
    check_payment_provider(provider_name, runtime, order.currency)
    provider = get_payment_provider(provider_name)
    if order.kind == OrderKind.lucky:
        lucky.ensure_available(runtime)
        await lucky.fix_client_seed(session, order, client_seed)

    payments = (await session.execute(select(Payment).where(Payment.order_id == order.id).order_by(Payment.created_at))).scalars().all()
    for existing in payments:
        if (
            existing.provider == provider_name
            and existing.status in OPEN_PAYMENT
            and existing.pay_url
            and (existing.expires_at is None or existing.expires_at > now + timedelta(minutes=1))
        ):
            return existing

    user = await session.get(User, order.user_id)
    assert user is not None
    payment = Payment(
        id=uuid.uuid4(),
        order_id=order.id,
        provider=provider_name,
        idempotency_key=f"{order.id}:{provider_name}:{len(payments) + 1}",
        status=PaymentStatus.created,
        amount=order.total,
        currency=order.currency,
        is_demo=provider.is_demo,
    )
    session.add(payment)
    await session.flush()

    ttl = int((order.expires_at - now).total_seconds()) if order.expires_at else get_settings().order_payment_ttl_minutes * 60
    description = f"{item_title(order.stars_amount, order.premium_months)} · заказ #{order.number}"
    if order.kind == OrderKind.lucky:
        description = f"Lucky Buy: шанс получить {description}"
    ctx = PaymentContext(
        order=order,
        user=user,
        description=description,
        return_url=templates.order_url(order),
        ttl_seconds=ttl,
    )
    try:
        intent = await provider.create_payment(payment, ctx)
    except PaymentProviderError as exc:
        payment.status = PaymentStatus.failed
        payment.last_error = exc.message
        add_event(
            session,
            order,
            "payment_create_failed",
            actor_type=ActorType.provider,
            actor_id=provider_name,
            message=exc.message,
            public=False,
        )
        raise

    payment.provider_payment_id = intent.provider_payment_id
    payment.pay_url = intent.pay_url
    payment.pay_url_kind = intent.pay_url_kind
    payment.expires_at = intent.expires_at
    payment.status = PaymentStatus.pending
    payment.provider_data = scrub(intent.data) or None
    order.payment_provider = provider_name
    # Other providers' open invoices are superseded (a late capture there is
    # still handled correctly as a regular or duplicate payment).
    for other in payments:
        if other.status in OPEN_PAYMENT and other.provider != provider_name:
            other.status = PaymentStatus.cancelled
    if order.status == OrderStatus.created:
        transition(
            session, order, OrderStatus.pending_payment, actor_type=ActorType.user, actor_id=user.telegram_id, message="Ожидается оплата"
        )
    add_event(
        session,
        order,
        "payment_created",
        actor_type=ActorType.provider,
        actor_id=provider_name,
        message=provider.title,
        data={"payment_id": str(payment.id)},
        public=False,
    )
    if notify_user:
        await notify.notify_order(
            session, order, "awaiting_payment", templates.awaiting_payment(order, payment.pay_url, payment.pay_url_kind), runtime
        )
    return payment


# ---------------------------------------------------------------------------
# Applying provider state (webhook / poll / demo)
# ---------------------------------------------------------------------------


async def _find_payment(session: AsyncSession, provider: str, state: ProviderPaymentState) -> Payment | None:
    payment = None
    if state.provider_payment_id:
        payment = (
            await session.execute(
                select(Payment).where(Payment.provider == provider, Payment.provider_payment_id == state.provider_payment_id)
            )
        ).scalar_one_or_none()
    if payment is None and state.reference:
        try:
            ref = uuid.UUID(state.reference)
        except ValueError:
            return None
        payment = (await session.execute(select(Payment).where(Payment.id == ref, Payment.provider == provider))).scalar_one_or_none()
    return payment


async def apply_state(
    session: AsyncSession, payment: Payment, state: ProviderPaymentState, runtime: RuntimeSettings, *, source: str
) -> str:
    """Apply a *verified* provider state. Idempotent. Returns a short result
    code for the webhook log."""
    order = await lock_order(session, payment.order_id)
    payment = (
        await session.execute(select(Payment).where(Payment.id == payment.id).with_for_update().execution_options(populate_existing=True))
    ).scalar_one()

    if state.reference and state.reference != str(payment.id):
        add_event(
            session,
            order,
            "payment_reference_mismatch",
            actor_type=ActorType.provider,
            actor_id=payment.provider,
            public=False,
            data={"source": source},
        )
        return "reference_mismatch"
    if payment.provider_payment_id and state.provider_payment_id and state.provider_payment_id != payment.provider_payment_id:
        return "provider_id_mismatch"

    if state.status == "paid":
        return await _confirm(session, order, payment, state, runtime, source=source)

    if payment.status in OPEN_PAYMENT:
        if state.status in ("expired", "failed", "cancelled"):
            payment.status = PaymentStatus(state.status)
            payment.last_error = f"provider reported {state.status}"
            add_event(
                session,
                order,
                f"payment_{state.status}",
                actor_type=ActorType.provider,
                actor_id=payment.provider,
                message="Оплата не прошла" if state.status == "failed" else None,
                data={"source": source},
            )
            return state.status
        if state.status == "pending" and payment.status == PaymentStatus.created:
            payment.status = PaymentStatus.pending
    return "noop"


async def _confirm(
    session: AsyncSession, order: Order, payment: Payment, state: ProviderPaymentState, runtime: RuntimeSettings, *, source: str
) -> str:
    if payment.status in (PaymentStatus.succeeded, PaymentStatus.refund_pending, PaymentStatus.refunded):
        return "already_processed"

    if (
        state.amount is None
        or state.currency is None
        or state.amount != payment.amount
        or state.currency.upper() != payment.currency.upper()
    ):
        payment.last_error = f"amount mismatch: got {state.amount} {state.currency}, expected {payment.amount} {payment.currency}"
        add_event(
            session,
            order,
            "payment_amount_mismatch",
            actor_type=ActorType.provider,
            actor_id=payment.provider,
            public=False,
            data={"got": f"{state.amount} {state.currency}", "expected": f"{payment.amount} {payment.currency}", "source": source},
        )
        await notify.admin_attention(
            session, order, "Сумма или валюта платежа не совпадает с заказом — нужна ручная проверка", runtime, f"mismatch:{payment.id}"
        )
        return "amount_mismatch"

    payment.paid_amount = state.paid_amount or str(state.amount)
    payment.paid_asset = state.paid_asset or state.currency
    payment.confirmed_at = utcnow()
    payment.provider_data = {**(payment.provider_data or {}), "confirmation": scrub(state.data)}

    if order.status not in (OrderStatus.created, OrderStatus.pending_payment, OrderStatus.cancelled):
        # The order is already paid (or closed after payment): this is a
        # second capture. Never mark it succeeded — return the money.
        payment.status = PaymentStatus.refund_pending
        payment.is_duplicate = True
        payment.refund_reason = "Повторная оплата уже оплаченного заказа"
        payment.refund_next_at = utcnow()
        add_event(
            session,
            order,
            "duplicate_payment",
            actor_type=ActorType.provider,
            actor_id=payment.provider,
            public=False,
            data={"payment_id": str(payment.id)},
        )
        await notify.admin_attention(
            session, order, "Получена повторная оплата — запущен автоматический возврат", runtime, f"dup:{payment.id}"
        )
        return "duplicate_refund"

    late = order.status == OrderStatus.cancelled
    payment.status = PaymentStatus.succeeded
    transition(
        session,
        order,
        OrderStatus.paid,
        actor_type=ActorType.provider,
        actor_id=payment.provider,
        message="Оплата подтверждена",
        event_type="late_payment" if late else "payment_confirmed",
        data={"payment_id": str(payment.id), "source": source},
    )
    if late:
        # Reservations were released on cancellation; take them again.
        await promo_service.apply(session, order)
        if order.bonus_spent > 0:
            try:
                await bonuses.debit(
                    session, order.user_id, order.bonus_spent, kind="order_spend", dedup_key=f"spend_late:{order.id}", order_id=order.id
                )
            except Conflict:
                add_event(session, order, "late_payment_bonus_shortfall", public=False, message="Бонусы уже потрачены")
    else:
        await promo_service.apply(session, order)

    draw = None
    if order.kind == OrderKind.lucky:
        # Same transaction as the payment: a captured attempt is always drawn, exactly once.
        draw = await lucky.draw(session, order)
        result = {"roll": lucky.roll_str(draw.roll_bp or 0), "chance": lucky.percent_str(draw.chance_bp)}
        if not draw.won:
            order.cost_amount = ZERO
            transition(
                session,
                order,
                OrderStatus.lost,
                message=f"Не повезло: выпало {lucky.ru(result['roll'])}, нужно меньше {lucky.ru(result['chance'])}",
                event_type="lucky_lost",
                data=result,
            )
            await notify.notify_order(session, order, "lucky_lost", templates.lucky_lost(order, draw), runtime)
            await _notify_admins_paid(session, order, draw, runtime)
            return "confirmed"
        order.cost_amount = draw.prize_cost
        add_event(
            session,
            order,
            "lucky_won",
            message=f"Повезло! Выпало {lucky.ru(result['roll'])} при шансе {lucky.ru(result['chance'])}%",
            data=result,
        )

    session.add(
        DeliveryTask(
            order_id=order.id,
            provider=order.delivery_provider,
            idempotency_key=f"dlv-{order.id}",
            max_attempts=get_settings().delivery_max_attempts,
            status=DeliveryStatus.queued,
            next_attempt_at=utcnow(),
        )
    )
    message = templates.lucky_won(order, draw) if draw is not None else templates.payment_confirmed(order)
    await notify.notify_order(session, order, "payment_confirmed", message, runtime)
    await _notify_admins_paid(session, order, draw, runtime)
    return "confirmed"


async def _notify_admins_paid(session: AsyncSession, order: Order, draw: LuckyDraw | None, runtime: RuntimeSettings) -> None:
    if runtime.notifications.admin_new_paid_order:
        user = await session.get(User, order.user_id)
        await notify.notify_admins(
            session, "admin_paid_order", templates.admin_paid_order(order, user.username if user else None, draw), f"paid:{order.id}"
        )


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


async def handle_webhook(
    session: AsyncSession, provider_name: str, headers: dict[str, str], body: bytes, remote_ip: str | None, runtime: RuntimeSettings
) -> dict[str, Any]:
    provider = get_payment_provider(provider_name)
    headers = {k.lower(): v for k, v in headers.items()}
    try:
        verified = await provider.parse_webhook(headers, body)
    except WebhookSignatureError:
        await _log_rejected(provider_name, body, remote_ip, "invalid signature")
        raise Unauthorized("invalid signature", code="signature_invalid") from None
    except (ValueError, KeyError) as exc:
        await _log_rejected(provider_name, body, remote_ip, f"malformed payload: {exc.__class__.__name__}")
        raise ValidationFailed("malformed payload", code="malformed_webhook") from None

    event_row_id = (
        await session.execute(
            insert(PaymentWebhookEvent)
            .values(
                provider=provider_name,
                event_id=verified.event_id,
                event_type=verified.event_type,
                signature_valid=True,
                status=WebhookStatus.received,
                payload=scrub(verified.payload),
                remote_ip=remote_ip,
            )
            .on_conflict_do_nothing(constraint="uq_webhook_provider_event")
            .returning(PaymentWebhookEvent.id)
        )
    ).scalar_one_or_none()
    if event_row_id is None:
        return {"ok": True, "duplicate": True}

    event = await session.get(PaymentWebhookEvent, event_row_id)
    assert event is not None
    if verified.state is None:
        event.status = WebhookStatus.ignored
        event.processed_at = utcnow()
        return {"ok": True, "ignored": True}

    payment = await _find_payment(session, provider_name, verified.state)
    if payment is None:
        event.status = WebhookStatus.ignored
        event.error = "unknown payment"
        event.processed_at = utcnow()
        return {"ok": True, "ignored": True}

    result = await apply_state(session, payment, verified.state, runtime, source="webhook")
    event.payment_id = payment.id
    event.status = WebhookStatus.processed
    event.error = None if result in ("confirmed", "already_processed", "noop", "duplicate_refund") else result
    event.processed_at = utcnow()
    return {"ok": True, "result": result}


async def _log_rejected(provider: str, body: bytes, remote_ip: str | None, error: str) -> None:
    """Persist a rejected webhook in its own transaction, without event_id."""
    from ..database.session import session_scope

    try:
        snippet: Any = body[:2000].decode("utf-8", "replace")
    except Exception:  # pragma: no cover
        snippet = None
    async with session_scope() as s:
        s.add(
            PaymentWebhookEvent(
                provider=provider,
                event_id=None,
                signature_valid=False,
                status=WebhookStatus.rejected,
                payload={"raw": scrub(snippet)},
                remote_ip=remote_ip,
                error=error,
            )
        )
    log.warning("webhook rejected", extra={"provider": provider, "remote_ip": remote_ip, "reason": error})


async def log_failed_webhook(provider: str, body: bytes, remote_ip: str | None, error: str) -> None:
    from ..database.session import session_scope

    async with session_scope() as s:
        s.add(
            PaymentWebhookEvent(
                provider=provider,
                event_id=None,
                signature_valid=True,
                status=WebhookStatus.failed,
                payload={"raw": scrub(body[:2000].decode("utf-8", "replace"))},
                remote_ip=remote_ip,
                error=error[:500],
            )
        )


# ---------------------------------------------------------------------------
# Reconciliation (server-side status query)
# ---------------------------------------------------------------------------


async def reconcile(session: AsyncSession, payment: Payment, runtime: RuntimeSettings, *, source: str = "poll") -> str:
    provider = get_payment_provider(payment.provider)
    state = await provider.fetch_state(payment)
    return await apply_state(session, payment, state, runtime, source=source)


async def reconcile_order(session: AsyncSession, order: Order, runtime: RuntimeSettings, *, source: str) -> str:
    payments = (
        (
            await session.execute(
                select(Payment).where(
                    Payment.order_id == order.id, Payment.status.in_(OPEN_PAYMENT + (PaymentStatus.cancelled, PaymentStatus.expired))
                )
            )
        )
        .scalars()
        .all()
    )
    result = "no_payments"
    for payment in payments:
        if not payment.provider_payment_id:
            continue
        result = await reconcile(session, payment, runtime, source=source)
        if result == "confirmed":
            break
    return result


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------


async def request_refund(
    session: AsyncSession, order: Order, runtime: RuntimeSettings, *, admin_id: int, reason: str, allow_completed: bool
) -> Payment:
    order = await lock_order(session, order.id)
    if order.status == OrderStatus.processing:
        raise Conflict("Заказ сейчас доставляется. Дождитесь результата или отметьте доставку неуспешной", code="refund_while_processing")
    if order.status == OrderStatus.completed and not allow_completed:
        raise Conflict("Заказ выполнен: Stars уже доставлены. Возврат доступен только владельцу", code="refund_completed_forbidden")
    if order.status == OrderStatus.lost and not allow_completed:
        raise Conflict(
            "Попытка Lucky Buy не выиграла: оплата не возвращается. Исключительный возврат доступен только владельцу",
            code="refund_lost_forbidden",
        )
    if order.status not in (OrderStatus.paid, OrderStatus.failed, OrderStatus.completed, OrderStatus.lost):
        raise Conflict("Возврат недоступен для текущего статуса", code="refund_not_allowed")
    payment = (
        await session.execute(
            select(Payment).where(Payment.order_id == order.id, Payment.status == PaymentStatus.succeeded).with_for_update()
        )
    ).scalar_one_or_none()
    if payment is None:
        raise NotFound("Подтверждённый платёж не найден", code="payment_not_found")

    task = (await session.execute(select(DeliveryTask).where(DeliveryTask.order_id == order.id).with_for_update())).scalar_one_or_none()
    if task is not None:
        if task.status in (DeliveryStatus.in_progress, DeliveryStatus.waiting_provider):
            raise Conflict("Доставка в процессе у поставщика — возврат пока невозможен", code="refund_while_processing")
        if task.status != DeliveryStatus.succeeded:
            task.status = DeliveryStatus.cancelled

    payment.status = PaymentStatus.refund_pending
    payment.refund_reason = reason
    payment.refund_next_at = utcnow()
    transition(
        session,
        order,
        OrderStatus.refund_pending,
        actor_type=ActorType.admin,
        actor_id=admin_id,
        message="Оформлен возврат",
        data={"reason": reason},
    )
    await notify.notify_order(session, order, "refund_requested", templates.refund_requested(order), runtime)
    return payment


async def process_refund(session: AsyncSession, payment_id: uuid.UUID, runtime: RuntimeSettings) -> str:
    """Executed by the worker. Network call happens under the payment lock,
    bounded by the provider timeout."""
    payment = (
        await session.execute(select(Payment).where(Payment.id == payment_id).with_for_update(skip_locked=True))
    ).scalar_one_or_none()
    if payment is None or payment.status != PaymentStatus.refund_pending:
        return "skip"
    order = await lock_order(session, payment.order_id)
    user = await session.get(User, order.user_id)
    assert user is not None
    provider = get_payment_provider(payment.provider)
    try:
        result = await provider.refund(payment, order, user)
    except PaymentProviderError as exc:
        payment.refund_attempts += 1
        payment.last_error = exc.message
        if exc.retryable and payment.refund_attempts < 6:
            payment.refund_next_at = utcnow() + timedelta(minutes=2**payment.refund_attempts)
        else:
            payment.refund_next_at = None  # needs a human
            await notify.admin_attention(
                session,
                order,
                f"Автоматический возврат не выполнен: {exc.message}. Верните средства вручную и подтвердите в админке",
                runtime,
                f"refund_fail:{payment.id}",
            )
        add_event(
            session, order, "refund_failed", actor_type=ActorType.provider, actor_id=payment.provider, message=exc.message, public=False
        )
        return "error"
    if result.status == "pending":
        payment.refund_next_at = utcnow() + timedelta(minutes=5)
        return "pending"
    await _finish_refund(session, order, payment, result.reference, runtime, actor_type=ActorType.provider, actor_id=payment.provider)
    return "refunded"


async def confirm_manual_refund(
    session: AsyncSession, order: Order, payment: Payment, reference: str, runtime: RuntimeSettings, admin_id: int
) -> None:
    order = await lock_order(session, order.id)
    payment = (await session.execute(select(Payment).where(Payment.id == payment.id).with_for_update())).scalar_one()
    if payment.status != PaymentStatus.refund_pending:
        raise Conflict("Платёж не ожидает возврата", code="refund_not_pending")
    await _finish_refund(session, order, payment, reference, runtime, actor_type=ActorType.admin, actor_id=admin_id, manual=True)


async def _finish_refund(
    session: AsyncSession,
    order: Order,
    payment: Payment,
    reference: str | None,
    runtime: RuntimeSettings,
    *,
    actor_type: ActorType,
    actor_id,
    manual: bool = False,
) -> None:
    payment.status = PaymentStatus.refunded
    payment.refunded_at = utcnow()
    payment.refund_reference = reference
    payment.refund_next_at = None
    add_event(
        session,
        order,
        "payment_refunded",
        actor_type=actor_type,
        actor_id=actor_id,
        public=False,
        data={"payment_id": str(payment.id), "reference": reference, "manual": manual, "duplicate": payment.is_duplicate},
    )
    if payment.is_duplicate or order.status != OrderStatus.refund_pending:
        return
    transition(session, order, OrderStatus.refunded, actor_type=actor_type, actor_id=actor_id, message="Возврат выполнен")
    await release_reservations(session, order)
    await referrals.on_order_refunded(session, order)
    await notify.notify_order(session, order, "refunded", templates.refunded(order), runtime)
