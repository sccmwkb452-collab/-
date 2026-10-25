"""Purchases and refunds.

A purchase is one database transaction:
lock buyer row -> idempotency check -> reserve a unit with SKIP LOCKED ->
create order -> debit balance -> referral reward -> commit.
The unit content is shown to the buyer only after the commit succeeded.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import (
    ItemStatus,
    Order,
    OrderStatus,
    Product,
    ProductItem,
    Transaction,
    TxKind,
    User,
)
from referrals.service import reward_for_order
from services import shop_settings
from services.audit import log_action
from services.errors import (
    AccessRestricted,
    InsufficientFunds,
    OutOfStock,
    PriceChanged,
    ProductUnavailable,
    ShopError,
)
from services.ledger import change_balance


def new_nonce() -> str:
    return secrets.token_urlsafe(6)


def idempotency_key(user_id: int, product_id: int, nonce: str) -> str:
    return f"{user_id}:{product_id}:{nonce}"


@dataclass(frozen=True)
class PurchaseResult:
    order: Order
    content: str
    created: bool  # False when this confirmation was already processed earlier
    referral_tx: Transaction | None = None


async def purchase(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    product_id: int,
    expected_price: int,
    nonce: str,
) -> PurchaseResult:
    key = idempotency_key(user_id, product_id, nonce)
    try:
        async with sessionmaker() as session, session.begin():
            return await _purchase_tx(session, user_id, product_id, expected_price, key)
    except IntegrityError:
        # A concurrent request with the same key won the race.
        async with sessionmaker() as session:
            existing = await session.scalar(select(Order).where(Order.idempotency_key == key))
            if existing is None:
                raise
            return PurchaseResult(existing, existing.item.content, created=False)


async def _purchase_tx(
    session: AsyncSession, user_id: int, product_id: int, expected_price: int, key: str
) -> PurchaseResult:
    # Serializes all purchases of one buyer: double taps queue up here.
    user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise ShopError("Пользователь не найден, отправьте /start")

    existing = await session.scalar(select(Order).where(Order.idempotency_key == key))
    if existing is not None:
        return PurchaseResult(existing, existing.item.content, created=False)

    if user.is_banned:
        raise AccessRestricted()

    product = await session.get(Product, product_id)
    if product is None or product.is_archived or not product.category.is_active:
        raise ProductUnavailable()
    if product.price != expected_price:
        raise PriceChanged(product.price)
    if user.balance < product.price:
        raise InsufficientFunds(product.price - user.balance)

    # SKIP LOCKED: concurrent buyers get different units; when the last unit is
    # taken by someone else's open transaction, we see none and report sold out.
    item = await session.scalar(
        select(ProductItem)
        .where(ProductItem.product_id == product_id, ProductItem.status == ItemStatus.AVAILABLE)
        .order_by(ProductItem.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if item is None:
        raise OutOfStock()

    order = Order(
        user_id=user_id,
        product_id=product_id,
        item_id=item.id,
        product_title=product.title,
        price=product.price,
        status=OrderStatus.COMPLETED,
        idempotency_key=key,
    )
    session.add(order)
    await session.flush()

    item.status = ItemStatus.SOLD
    item.sold_at = func.now()
    await change_balance(session, user_id, -product.price, TxKind.PURCHASE, order_id=order.id)

    settings = await shop_settings.load(session)
    referral_tx = await reward_for_order(session, order, user, settings)
    await session.flush()
    return PurchaseResult(order, item.content, created=True, referral_tx=referral_tx)


@dataclass(frozen=True)
class RefundResult:
    order: Order
    refunded: bool


async def refund_order(
    sessionmaker: async_sessionmaker[AsyncSession], order_id: int, admin_id: int, reason: str
) -> RefundResult:
    """Returns the money to the buyer. The unit is revoked and never resold."""
    async with sessionmaker() as session, session.begin():
        order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update(of=Order))
        if order is None:
            raise ShopError("Заказ не найден")
        if order.status != OrderStatus.COMPLETED:
            return RefundResult(order, refunded=False)
        order.status = OrderStatus.REFUNDED
        order.refunded_at = func.now()
        order.refund_reason = reason[:256]
        order.refunded_by = admin_id
        item = await session.get(ProductItem, order.item_id)
        if item is not None:
            item.status = ItemStatus.REVOKED
        await change_balance(
            session, order.user_id, order.price, TxKind.REFUND, order_id=order.id, admin_id=admin_id, comment=reason[:256]
        )
        await log_action(session, admin_id, "order_refund", order.number, reason)
        await session.flush()
        await session.refresh(order)
        return RefundResult(order, refunded=True)


async def user_orders(session: AsyncSession, user_id: int, limit: int, offset: int) -> tuple[list[Order], int]:
    total = await session.scalar(select(func.count(Order.id)).where(Order.user_id == user_id))
    rows = await session.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


def parse_order_number(text: str) -> int | None:
    text = text.strip().upper().lstrip("#").removeprefix("AM-").removeprefix("AM")
    return int(text) if text.isdigit() and int(text) < 2**62 else None
