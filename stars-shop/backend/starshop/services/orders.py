from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..database.enums import ActorType, OrderStatus, PaymentStatus, RecipientType, ShopMode
from ..database.models import Order, Payment, User
from ..delivery.base import DeliveryProvider
from ..delivery.registry import get_delivery_provider
from ..notifications import service as notify
from ..notifications import templates
from ..payments.registry import enabled_providers
from ..shared.errors import Conflict, Forbidden, NotFound, ServiceUnavailable, ValidationFailed
from ..shared.ids import order_number
from ..shared.timeutil import utcnow
from . import bonuses, pricing
from . import promo as promo_service
from .app_settings import RuntimeSettings
from .state_machine import OPEN_STATUSES, STATUS_GROUPS, add_event, transition

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


@dataclass(slots=True)
class RecipientInput:
    type: RecipientType
    username: str | None = None


@dataclass(slots=True)
class OrderInput:
    product_id: int
    stars_amount: int | None
    recipient: RecipientInput
    payment_provider: str
    promo_code: str | None = None
    use_bonus: bool = False


def normalize_username(raw: str | None) -> str:
    value = (raw or "").strip()
    if value.startswith("https://t.me/"):
        value = value.removeprefix("https://t.me/")
    value = value.lstrip("@").strip()
    if not USERNAME_RE.fullmatch(value):
        raise ValidationFailed(
            "Укажите username в формате @username: 5–32 символа, латиница, цифры и «_»",
            code="recipient_invalid",
        )
    return value


def current_mode(runtime: RuntimeSettings) -> ShopMode:
    return ShopMode(runtime.shop.mode)


def ensure_shop_open(runtime: RuntimeSettings) -> None:
    if runtime.shop.maintenance:
        raise ServiceUnavailable(runtime.shop.maintenance_message, code="maintenance")


def active_delivery_provider(runtime: RuntimeSettings) -> DeliveryProvider:
    provider = get_delivery_provider()
    if provider.is_demo and current_mode(runtime) != ShopMode.demo:
        raise ServiceUnavailable("Доставка не настроена", code="delivery_not_configured")
    if not provider.is_configured():
        raise ServiceUnavailable("Доставка временно недоступна", code="delivery_not_configured")
    return provider


async def resolve_recipient(
    user: User, recipient: RecipientInput, delivery: DeliveryProvider, runtime: RuntimeSettings, *, check_remote: bool
) -> tuple[RecipientType, str | None, int | None, str | None]:
    """Returns ``(type, username, telegram_id, display_name)``."""
    if recipient.type == RecipientType.self:
        if delivery.requires_username and not user.username:
            raise ValidationFailed(
                "Для зачисления звёзд нужен публичный username. Задайте его в настройках Telegram и откройте магазин заново",
                code="self_username_required",
            )
        return RecipientType.self, user.username, user.telegram_id, user.display_name
    if not (runtime.shop.allow_gift_to_others and delivery.supports_gift_to_others):
        raise ValidationFailed("Покупка для другого пользователя сейчас недоступна", code="gifts_disabled")
    username = normalize_username(recipient.username)
    if user.username and username.lower() == user.username.lower():
        return RecipientType.self, user.username, user.telegram_id, user.display_name
    display = None
    if check_remote:
        check = await delivery.check_recipient(username)
        if not check.ok:
            raise ValidationFailed(check.reason or "Получатель не найден", code="recipient_not_found")
        display = check.display_name
    return RecipientType.username, username, None, display


def check_payment_provider(name: str, runtime: RuntimeSettings) -> None:
    if name not in {p.name for p in enabled_providers(runtime.shop.mode)}:
        raise ValidationFailed("Этот способ оплаты сейчас недоступен", code="payment_method_unavailable")


async def create_order(
    session: AsyncSession, user: User, data: OrderInput, idempotency_key: str, runtime: RuntimeSettings
) -> tuple[Order, bool]:
    """Idempotent: the same ``(user, Idempotency-Key)`` always returns the
    same order. Returns ``(order, created)``."""
    if not 8 <= len(idempotency_key) <= 64:
        raise ValidationFailed("Некорректный ключ идемпотентности", code="idempotency_key_invalid")
    existing = (
        await session.execute(select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    ensure_shop_open(runtime)
    if user.is_blocked:
        raise Forbidden("Покупки для этого аккаунта ограничены. Обратитесь в поддержку", code="user_blocked")
    check_payment_provider(data.payment_provider, runtime)
    delivery = active_delivery_provider(runtime)

    open_count = await session.scalar(
        select(func.count()).select_from(Order).where(Order.user_id == user.id, Order.status.in_(OPEN_STATUSES))
    )
    if (open_count or 0) >= get_settings().max_open_orders_per_user:
        raise Conflict("У вас уже есть несколько неоплаченных заказов. Оплатите или отмените их", code="too_many_open_orders")

    product = await pricing.load_product(session, data.product_id)
    rtype, r_username, r_tg_id, r_name = await resolve_recipient(user, data.recipient, delivery, runtime, check_remote=True)
    # Lock the user row: serialises bonus spending across parallel orders.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    await session.refresh(user)
    quote = await pricing.build_quote(
        session,
        user=user,
        product=product,
        stars_requested=data.stars_amount,
        promo_code=data.promo_code,
        use_bonus=data.use_bonus,
        payment_provider=data.payment_provider,
        delivery=delivery,
        runtime=runtime,
        strict_promo=True,
        lock_promo=True,
    )
    if quote.total <= 0:
        raise ValidationFailed("Стоимость заказа должна быть больше нуля", code="invalid_total")

    order = Order(
        id=uuid.uuid4(),
        number=order_number(),
        user_id=user.id,
        product_id=product.id,
        product_kind=product.kind,
        stars_amount=quote.stars_amount,
        recipient_type=rtype,
        recipient_username=r_username,
        recipient_telegram_id=r_tg_id,
        recipient_name=r_name,
        unit_price=quote.unit_price,
        subtotal=quote.subtotal,
        discount_amount=quote.discount,
        bonus_spent=quote.bonus_spent,
        fee_amount=quote.fee,
        total=quote.total,
        cost_amount=quote.cost_amount,
        currency=quote.currency,
        status=OrderStatus.created,
        mode=current_mode(runtime),
        payment_provider=data.payment_provider,
        delivery_provider=delivery.name,
        promo_code_id=quote.promo.id if quote.promo else None,
        idempotency_key=idempotency_key,
        expires_at=utcnow() + timedelta(minutes=get_settings().order_payment_ttl_minutes),
    )
    for _ in range(3):
        try:
            async with session.begin_nested():
                session.add(order)
                await session.flush()
            break
        except IntegrityError as exc:
            if "uq_orders_user_idempotency" in str(exc.orig):
                # A parallel request with the same key won the race (the
                # savepoint rollback already detached our instance).
                winner = (
                    await session.execute(select(Order).where(Order.user_id == user.id, Order.idempotency_key == idempotency_key))
                ).scalar_one()
                return winner, False
            order.number = order_number()
    else:  # pragma: no cover
        raise Conflict("Не удалось создать заказ, попробуйте ещё раз")

    if quote.promo is not None:
        await promo_service.reserve(session, quote.promo, user, order, quote.discount)
    if quote.bonus_spent > 0:
        await bonuses.spend_for_order(session, user.id, order.id, quote.bonus_spent)
    add_event(
        session,
        order,
        "order_created",
        actor_type=ActorType.user,
        actor_id=user.telegram_id,
        message="Заказ создан",
        to_status=OrderStatus.created.value,
        data={"mode": str(order.mode)},
    )
    return order, True


async def release_reservations(session: AsyncSession, order: Order) -> None:
    await promo_service.release(session, order)
    if order.bonus_spent > 0:
        await bonuses.return_for_order(session, order.user_id, order.id, order.bonus_spent)


async def lock_order(session: AsyncSession, order_id: uuid.UUID) -> Order:
    order = (
        await session.execute(select(Order).where(Order.id == order_id).with_for_update().execution_options(populate_existing=True))
    ).scalar_one_or_none()
    if order is None:
        raise NotFound("Заказ не найден", code="order_not_found")
    return order


async def cancel_order(
    session: AsyncSession,
    order: Order,
    runtime: RuntimeSettings,
    *,
    actor_type: ActorType,
    actor_id: str | int | None,
    reason: str,
    event_type: str = "order_cancelled",
) -> list[Payment]:
    """Cancel an unpaid order. Returns open payments the caller should try to
    invalidate at the provider (outside the transaction)."""
    order = await lock_order(session, order.id)
    if order.status not in OPEN_STATUSES:
        raise Conflict("Заказ уже нельзя отменить", code="cannot_cancel")
    open_payments = (
        (
            await session.execute(
                select(Payment).where(Payment.order_id == order.id, Payment.status.in_((PaymentStatus.created, PaymentStatus.pending)))
            )
        )
        .scalars()
        .all()
    )
    for payment in open_payments:
        payment.status = PaymentStatus.cancelled if event_type == "order_cancelled" else PaymentStatus.expired
    transition(session, order, OrderStatus.cancelled, actor_type=actor_type, actor_id=actor_id, message=reason, event_type=event_type)
    await release_reservations(session, order)
    if event_type == "order_expired" and open_payments:
        await notify.notify_order(session, order, "order_expired", templates.order_expired(order), runtime)
    return list(open_payments)


async def get_user_order(session: AsyncSession, user: User, order_id: uuid.UUID, *, with_details: bool = False) -> Order:
    stmt = select(Order).where(Order.id == order_id, Order.user_id == user.id)
    if with_details:
        stmt = stmt.options(selectinload(Order.events), selectinload(Order.payments), selectinload(Order.delivery_task))
    order = (await session.execute(stmt)).scalar_one_or_none()
    if order is None:
        # Same answer for "does not exist" and "belongs to someone else".
        raise NotFound("Заказ не найден", code="order_not_found")
    return order


async def list_user_orders(session: AsyncSession, user: User, *, group: str | None, limit: int, offset: int) -> tuple[list[Order], int]:
    stmt = select(Order).where(Order.user_id == user.id)
    count_stmt = select(func.count()).select_from(Order).where(Order.user_id == user.id)
    if group and group != "all":
        statuses = STATUS_GROUPS.get(group)
        if statuses is None:
            raise ValidationFailed("Неизвестный фильтр", code="invalid_filter")
        stmt = stmt.where(Order.status.in_(statuses))
        count_stmt = count_stmt.where(Order.status.in_(statuses))
    total = await session.scalar(count_stmt) or 0
    rows = (await session.execute(stmt.order_by(Order.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return list(rows), total
