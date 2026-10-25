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


MAX_BULK = 50


@dataclass(frozen=True)
class PurchaseResult:
    order: Order
    content: str
    created: bool  # False when this confirmation was already processed earlier
    referral_tx: Transaction | None = None


@dataclass(frozen=True)
class BulkResult:
    """Several units of one product bought in one transaction."""

    items: list[PurchaseResult]
    created: bool

    @property
    def orders(self) -> list[Order]:
        return [r.order for r in self.items]

    @property
    def total(self) -> int:
        return sum(r.order.price for r in self.items)

    @property
    def referral_txs(self) -> list[Transaction]:
        return [r.referral_tx for r in self.items if r.referral_tx is not None]


def _keys(base: str, quantity: int) -> list[str]:
    return [base] if quantity == 1 else [f"{base}#{i}" for i in range(1, quantity + 1)]


async def purchase(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    product_id: int,
    expected_price: int,
    nonce: str,
) -> PurchaseResult:
    result = await purchase_many(
        sessionmaker, user_id=user_id, product_id=product_id, expected_price=expected_price, quantity=1, nonce=nonce
    )
    return result.items[0]


async def purchase_many(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    product_id: int,
    expected_price: int,
    quantity: int,
    nonce: str,
) -> BulkResult:
    """Buys `quantity` units at once: all of them or none, with a single balance check."""
    if not 1 <= quantity <= MAX_BULK:
        raise ShopError(f"Количество: от 1 до {MAX_BULK}")
    keys = _keys(idempotency_key(user_id, product_id, nonce), quantity)
    try:
        async with sessionmaker() as session, session.begin():
            return await _purchase_tx(session, user_id, product_id, expected_price, keys)
    except IntegrityError:
        # A concurrent request with the same key won the race.
        async with sessionmaker() as session:
            existing = await _existing(session, keys)
            if existing is None:
                raise
            return existing


async def _existing(session: AsyncSession, keys: list[str]) -> BulkResult | None:
    orders = list(
        (await session.execute(select(Order).where(Order.idempotency_key.in_(keys)).order_by(Order.id))).scalars()
    )
    if not orders:
        return None
    return BulkResult([PurchaseResult(o, o.item.content, created=False) for o in orders], created=False)


async def _purchase_tx(
    session: AsyncSession, user_id: int, product_id: int, expected_price: int, keys: list[str]
) -> BulkResult:
    # Serializes all purchases of one buyer: double taps queue up here.
    user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise ShopError("Пользователь не найден, отправьте /start")

    existing = await _existing(session, keys)
    if existing is not None:
        return existing

    if user.is_banned:
        raise AccessRestricted()

    product = await session.get(Product, product_id)
    if product is None or product.is_archived or not product.category.is_active:
        raise ProductUnavailable()
    if product.price != expected_price:
        raise PriceChanged(product.price)
    total = product.price * len(keys)
    if user.balance < total:
        raise InsufficientFunds(total - user.balance)

    # SKIP LOCKED: concurrent buyers get different units; when the last units are
    # taken by someone else's open transaction, we see fewer and report sold out.
    items = list(
        (
            await session.execute(
                select(ProductItem)
                .where(ProductItem.product_id == product_id, ProductItem.status == ItemStatus.AVAILABLE)
                .order_by(ProductItem.id)
                .limit(len(keys))
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    if len(items) < len(keys):
        raise OutOfStock(available=len(items))

    settings = await shop_settings.load(session)
    results = []
    for key, item in zip(keys, items):
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
        referral_tx = await reward_for_order(session, order, user, settings)
        results.append(PurchaseResult(order, item.content, created=True, referral_tx=referral_tx))
    await session.flush()
    return BulkResult(results, created=True)


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
