"""Referral bonuses paid out as Telegram Stars.

1. The user asks for N Stars. Their price at the withdrawal rate is held
   (debited from the bonus balance) at once, so it cannot be spent twice.
2. An administrator approves (or the shop approves automatically): a regular
   Stars order for the user's own account is created, already paid with the
   bonuses, and goes through the same delivery as any order.
3. A rejected request, or an approved one whose delivery finally failed,
   gives the bonuses back. Every movement is idempotent (bonus ledger keys).
"""

from __future__ import annotations

import uuid
from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import ActorType, DeliveryStatus, OrderKind, OrderStatus, ProductKind, RecipientType, WithdrawalStatus
from ..database.models import DeliveryTask, Order, Product, User, Withdrawal
from ..notifications import service as notify
from ..notifications.templates import Message, fmt_money, fmt_stars, order_button
from ..shared.errors import Conflict, Forbidden, NotFound, ValidationFailed
from ..shared.ids import order_number
from ..shared.money import money
from ..shared.timeutil import utcnow
from . import bonuses
from .app_settings import RuntimeSettings
from .orders import active_delivery_provider, current_mode, ensure_shop_open
from .state_machine import add_event, transition

PROVIDER = "bonus"  # the "payment" of a withdrawal order: bonuses held at request time


async def custom_product(session: AsyncSession) -> Product | None:
    return (
        await session.execute(
            select(Product).where(Product.kind == ProductKind.custom, Product.is_archived.is_(False)).order_by(Product.id).limit(1)
        )
    ).scalar_one_or_none()


async def rate(session: AsyncSession, runtime: RuntimeSettings) -> Decimal | None:
    """Bonus roubles per Star: the admin setting or the price of «Своё количество»."""
    if runtime.referral.withdrawal_rate:
        return Decimal(runtime.referral.withdrawal_rate)
    product = await custom_product(session)
    return Decimal(product.price_per_star) if product and product.price_per_star else None


async def pending_for(session: AsyncSession, user: User) -> Withdrawal | None:
    return (
        await session.execute(select(Withdrawal).where(Withdrawal.user_id == user.id, Withdrawal.status == WithdrawalStatus.pending))
    ).scalar_one_or_none()


async def overview(session: AsyncSession, user: User, runtime: RuntimeSettings) -> dict:
    cfg = runtime.referral
    per_star = await rate(session, runtime)
    available = int((Decimal(user.bonus_balance) / per_star).to_integral_value(rounding=ROUND_FLOOR)) if per_star else 0
    items = (
        (await session.execute(select(Withdrawal).where(Withdrawal.user_id == user.id).order_by(Withdrawal.id.desc()).limit(20)))
        .scalars()
        .all()
    )
    orders = {
        o.id: o for o in (await session.execute(select(Order).where(Order.id.in_([w.order_id for w in items if w.order_id])))).scalars()
    }
    return {
        "enabled": bool(cfg.enabled and cfg.withdrawal_enabled and per_star),
        "rate": str(per_star) if per_star else None,
        "min_stars": cfg.withdrawal_min_stars,
        "available_stars": available,
        "needs_username": not user.username,
        "items": [serialize(w, orders.get(w.order_id)) for w in items],
    }


def serialize(w: Withdrawal, order: Order | None = None) -> dict:
    return {
        "id": w.id,
        "stars": w.stars,
        "amount": str(money(w.amount)),
        "status": w.status,
        "comment": w.comment,
        "created_at": w.created_at.isoformat(),
        "decided_at": w.decided_at.isoformat() if w.decided_at else None,
        "order": {"id": str(order.id), "number": order.number, "status": order.status} if order else None,
    }


async def request(session: AsyncSession, user: User, stars: int, runtime: RuntimeSettings) -> Withdrawal:
    cfg = runtime.referral
    ensure_shop_open(runtime)
    if not (cfg.enabled and cfg.withdrawal_enabled):
        raise ValidationFailed("Вывод бонусов сейчас недоступен", code="withdrawal_disabled")
    if user.is_blocked:
        raise Forbidden("Операции для этого аккаунта ограничены. Обратитесь в поддержку", code="user_blocked")
    per_star = await rate(session, runtime)
    if per_star is None:
        raise ValidationFailed("Вывод бонусов сейчас недоступен", code="withdrawal_disabled")
    delivery = active_delivery_provider(runtime)
    if delivery.requires_username and not user.username:
        raise ValidationFailed(
            "Для зачисления звёзд нужен публичный username. Задайте его в настройках Telegram и откройте магазин заново",
            code="self_username_required",
        )
    low = max(cfg.withdrawal_min_stars, delivery.min_stars)
    if not low <= stars <= delivery.max_stars:
        raise ValidationFailed(
            f"Вывести можно от {low} до {delivery.max_stars} звёзд", code="withdrawal_out_of_range", details={"min": low}
        )
    # The user row lock serialises requests and bonus spending.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    await session.refresh(user)
    if await pending_for(session, user) is not None:
        raise Conflict("У вас уже есть заявка на вывод. Дождитесь её рассмотрения", code="withdrawal_pending")
    amount = money(per_star * stars)
    if amount > user.bonus_balance:
        raise ValidationFailed("Недостаточно бонусов для такого вывода", code="insufficient_bonus")
    withdrawal = Withdrawal(user_id=user.id, stars=stars, amount=amount, rate=per_star, recipient_username=user.username)
    session.add(withdrawal)
    await session.flush()
    await bonuses.debit(
        session, user.id, amount, kind="withdrawal", dedup_key=f"withdrawal:{withdrawal.id}", comment=f"Вывод {stars} Stars"
    )
    if cfg.withdrawal_auto_approve:
        await approve(session, withdrawal, runtime, admin_id=None)
    else:
        await notify.notify_admins(
            session,
            "withdrawal_requested",
            Message(
                f"💸 <b>Заявка на вывод #{withdrawal.id}</b>\n{fmt_stars(stars)} Stars · {fmt_money(amount, get_settings().shop_currency)} бонусами\n"
                f"Пользователь: {'@' + user.username if user.username else user.telegram_id}",
                {"inline_keyboard": [[{"text": "Открыть в админке", "url": f"{get_settings().admin_url}withdrawals"}]]},
            ),
            dedup_key=f"withdrawal_requested:{withdrawal.id}",
        )
    return withdrawal


async def _lock(session: AsyncSession, withdrawal_id: int) -> Withdrawal:
    w = (
        await session.execute(
            select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if w is None:
        raise NotFound("Заявка не найдена", code="withdrawal_not_found")
    return w


async def approve(session: AsyncSession, withdrawal: Withdrawal, runtime: RuntimeSettings, *, admin_id: int | None) -> Order:
    w = await _lock(session, withdrawal.id)
    if w.status != WithdrawalStatus.pending:
        raise Conflict("Заявка уже рассмотрена", code="withdrawal_decided")
    user = await session.get(User, w.user_id)
    assert user is not None
    delivery = active_delivery_provider(runtime)
    product = await custom_product(session)
    cost = money(Decimal(product.cost_per_star) * w.stars) if product and product.cost_per_star is not None else None
    order = Order(
        id=uuid.uuid4(),
        number=order_number(),
        user_id=user.id,
        product_id=product.id if product else None,
        product_kind=ProductKind.custom,
        kind=OrderKind.withdrawal,
        stars_amount=w.stars,
        recipient_type=RecipientType.self,
        recipient_username=user.username or w.recipient_username,
        recipient_telegram_id=user.telegram_id,
        recipient_name=user.display_name,
        unit_price=w.rate,
        subtotal=w.amount,
        bonus_spent=w.amount,
        total=Decimal("0"),
        cost_amount=cost,
        currency=get_settings().shop_currency,
        status=OrderStatus.created,
        mode=current_mode(runtime),
        payment_provider=PROVIDER,
        delivery_provider=delivery.name,
        idempotency_key=f"withdrawal-{w.id}",
    )
    session.add(order)
    await session.flush()
    actor = (ActorType.admin, admin_id) if admin_id else (ActorType.system, None)
    add_event(
        session,
        order,
        "order_created",
        actor_type=actor[0],
        actor_id=actor[1],
        message=f"Вывод бонусов, заявка #{w.id}",
        to_status="created",
    )
    transition(session, order, OrderStatus.pending_payment, actor_type=actor[0], actor_id=actor[1])
    transition(
        session,
        order,
        OrderStatus.paid,
        actor_type=actor[0],
        actor_id=actor[1],
        message="Оплачено бонусами",
        event_type="payment_confirmed",
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
    w.status = WithdrawalStatus.approved
    w.order_id = order.id
    w.decided_by = admin_id
    w.decided_at = utcnow()
    await notify.notify_order(
        session,
        order,
        "withdrawal_approved",
        Message(
            f"💸 <b>Вывод одобрен</b>\n{fmt_stars(w.stars)} Stars отправляем на ваш аккаунт. Заказ #{order.number}.",
            {"inline_keyboard": [[order_button(order)]]},
        ),
        runtime,
    )
    return order


async def reject(session: AsyncSession, withdrawal: Withdrawal, runtime: RuntimeSettings, *, admin_id: int, comment: str) -> Withdrawal:
    w = await _lock(session, withdrawal.id)
    if w.status != WithdrawalStatus.pending:
        raise Conflict("Заявка уже рассмотрена", code="withdrawal_decided")
    await bonuses.credit(
        session, w.user_id, w.amount, kind="withdrawal_return", dedup_key=f"withdrawal_return:{w.id}", comment=comment[:255]
    )
    w.status = WithdrawalStatus.rejected
    w.comment = comment
    w.decided_by = admin_id
    w.decided_at = utcnow()
    await _notify_user(session, w, runtime, f"↩️ <b>Заявка на вывод #{w.id} отклонена</b>\nБонусы вернулись на баланс. Причина: {comment}")
    return w


async def return_failed(session: AsyncSession, withdrawal: Withdrawal, runtime: RuntimeSettings, *, admin_id: int) -> Withdrawal:
    """The Stars could not be delivered: close the order and give the bonuses back."""
    w = await _lock(session, withdrawal.id)
    order = await session.get(Order, w.order_id) if w.order_id else None
    if w.status != WithdrawalStatus.approved or order is None or order.status != OrderStatus.failed:
        raise Conflict("Вернуть бонусы можно только по выводу с неуспешной доставкой", code="withdrawal_not_failed")
    transition(session, order, OrderStatus.refund_pending, actor_type=ActorType.admin, actor_id=admin_id, message="Возврат бонусов")
    transition(session, order, OrderStatus.refunded, actor_type=ActorType.admin, actor_id=admin_id, message="Бонусы возвращены")
    await bonuses.credit(session, w.user_id, w.amount, kind="withdrawal_return", dedup_key=f"withdrawal_return:{w.id}", order_id=order.id)
    w.status = WithdrawalStatus.returned
    w.decided_by = admin_id
    await _notify_user(session, w, runtime, f"↩️ <b>Вывод #{w.id} не выполнен</b>\nЗвёзды не удалось отправить, бонусы вернулись на баланс.")
    return w


async def _notify_user(session: AsyncSession, w: Withdrawal, runtime: RuntimeSettings, text: str) -> None:
    if not runtime.notifications.user_notifications:
        return
    user = await session.get(User, w.user_id)
    if user is not None:
        await notify.enqueue(
            session,
            chat_id=user.telegram_id,
            kind="withdrawal",
            message=Message(text, None),
            dedup_key=f"withdrawal:{w.id}:{w.status}",
            user_id=user.id,
        )
