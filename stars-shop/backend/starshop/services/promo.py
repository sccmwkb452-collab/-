"""Promo codes: validation, reservation and usage accounting.

A usage is *reserved* when the order is created (counts towards limits, so
two parallel orders cannot both take the last use), becomes *applied* once
the payment is confirmed and is *released* if the order is cancelled or
refunded.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import OrderStatus, PromoKind, PromoUsageStatus
from ..database.models import Order, PromoCode, PromoCodeUsage, User
from ..shared.errors import ValidationFailed
from ..shared.money import money, percent_of
from ..shared.timeutil import utcnow
from .state_machine import PAID_STATUSES

ACTIVE_USAGE = (PromoUsageStatus.reserved, PromoUsageStatus.applied)


def normalize_code(code: str) -> str:
    return code.strip().upper()


def compute_discount(promo: PromoCode, subtotal: Decimal) -> Decimal:
    discount = percent_of(subtotal, promo.value) if promo.kind == PromoKind.percent else money(promo.value)
    if promo.max_discount is not None:
        discount = min(discount, money(promo.max_discount))
    return min(discount, subtotal)


async def validate(
    session: AsyncSession,
    raw_code: str,
    user: User,
    subtotal: Decimal,
    *,
    lock: bool = False,
    now: datetime | None = None,
) -> PromoCode:
    code = normalize_code(raw_code)
    if not code or len(code) > 32:
        raise ValidationFailed("Промокод не найден", code="promo_not_found")
    stmt = select(PromoCode).where(PromoCode.code == code)
    if lock:
        stmt = stmt.with_for_update()
    promo = (await session.execute(stmt)).scalar_one_or_none()
    if promo is None:
        raise ValidationFailed("Промокод не найден", code="promo_not_found")
    now = now or utcnow()
    if not promo.is_active:
        raise ValidationFailed("Промокод больше не действует", code="promo_inactive")
    if promo.starts_at and now < promo.starts_at:
        raise ValidationFailed("Промокод ещё не начал действовать", code="promo_not_started")
    if promo.expires_at and now >= promo.expires_at:
        raise ValidationFailed("Срок действия промокода истёк", code="promo_expired")
    if promo.min_order_amount is not None and subtotal < promo.min_order_amount:
        raise ValidationFailed(
            "Сумма заказа меньше минимальной для этого промокода",
            code="promo_min_amount",
            details={"min_order_amount": str(promo.min_order_amount)},
        )
    if promo.max_uses is not None:
        used = await session.scalar(
            select(func.count())
            .select_from(PromoCodeUsage)
            .where(PromoCodeUsage.promo_code_id == promo.id, PromoCodeUsage.status.in_(ACTIVE_USAGE))
        )
        if (used or 0) >= promo.max_uses:
            raise ValidationFailed("Лимит использований промокода исчерпан", code="promo_exhausted")
    used_by_user = await session.scalar(
        select(func.count())
        .select_from(PromoCodeUsage)
        .where(
            PromoCodeUsage.promo_code_id == promo.id,
            PromoCodeUsage.user_id == user.id,
            PromoCodeUsage.status.in_(ACTIVE_USAGE),
        )
    )
    if (used_by_user or 0) >= promo.per_user_limit:
        raise ValidationFailed("Вы уже использовали этот промокод", code="promo_user_limit")
    if promo.first_order_only:
        paid_orders = await session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.user_id == user.id, Order.status.in_(PAID_STATUSES | {OrderStatus.refunded}))
        )
        if paid_orders:
            raise ValidationFailed("Промокод действует только на первый заказ", code="promo_first_order_only")
    return promo


async def reserve(session: AsyncSession, promo: PromoCode, user: User, order: Order, discount: Decimal) -> None:
    session.add(
        PromoCodeUsage(
            promo_code_id=promo.id,
            user_id=user.id,
            order_id=order.id,
            status=PromoUsageStatus.reserved,
            discount_amount=discount,
        )
    )


async def _usage(session: AsyncSession, order: Order) -> PromoCodeUsage | None:
    return (await session.execute(select(PromoCodeUsage).where(PromoCodeUsage.order_id == order.id).with_for_update())).scalar_one_or_none()


async def apply(session: AsyncSession, order: Order) -> None:
    usage = await _usage(session, order)
    if usage is not None and usage.status != PromoUsageStatus.applied:
        usage.status = PromoUsageStatus.applied


async def release(session: AsyncSession, order: Order) -> None:
    usage = await _usage(session, order)
    if usage is not None and usage.status != PromoUsageStatus.released:
        usage.status = PromoUsageStatus.released
