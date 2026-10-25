from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from database.models import ItemStatus, Order, OrderStatus, ProductItem, Transaction, TxKind, User
from orders import service as orders
from services.errors import AccessRestricted, InsufficientFunds, OutOfStock, PriceChanged, ProductUnavailable
from tests.conftest import ADMIN_ID, make_product, make_user


async def balance(sm, user_id: int) -> int:
    async with sm() as s:
        return (await s.get(User, user_id)).balance


async def count(sm, stmt) -> int:
    async with sm() as s:
        return int(await s.scalar(stmt) or 0)


async def test_purchase_debits_and_delivers(sm):
    await make_user(sm, 10, balance=5000_00)
    product = await make_product(sm, price=1490_00, stock=2)

    result = await orders.purchase(sm, user_id=10, product_id=product.id, expected_price=1490_00, nonce="n1")

    assert result.created
    assert result.content.startswith("SECRET-")
    assert result.order.number == f"AM-{result.order.id:06d}"
    assert await balance(sm, 10) == 5000_00 - 1490_00
    async with sm() as s:
        item = await s.get(ProductItem, result.order.item_id)
        assert item.status == ItemStatus.SOLD
        tx = await s.scalar(select(Transaction).where(Transaction.order_id == result.order.id))
        assert tx.kind == TxKind.PURCHASE and tx.amount == -1490_00 and tx.balance_after == 3510_00


async def test_insufficient_funds_changes_nothing(sm):
    await make_user(sm, 11, balance=100_00)
    product = await make_product(sm, price=1490_00, stock=1)
    with pytest.raises(InsufficientFunds) as exc:
        await orders.purchase(sm, user_id=11, product_id=product.id, expected_price=1490_00, nonce="n")
    assert exc.value.needed == 1390_00
    assert await balance(sm, 11) == 100_00
    assert await count(sm, select(func.count(Order.id))) == 0
    assert await count(sm, select(func.count(ProductItem.id)).where(ProductItem.status == ItemStatus.AVAILABLE)) == 1


async def test_out_of_stock(sm):
    await make_user(sm, 12, balance=5000_00)
    product = await make_product(sm, stock=0)
    with pytest.raises(OutOfStock):
        await orders.purchase(sm, user_id=12, product_id=product.id, expected_price=product.price, nonce="n")
    assert await balance(sm, 12) == 5000_00


async def test_price_change_is_detected(sm):
    await make_user(sm, 13, balance=5000_00)
    product = await make_product(sm, price=1000_00)
    with pytest.raises(PriceChanged) as exc:
        await orders.purchase(sm, user_id=13, product_id=product.id, expected_price=900_00, nonce="n")
    assert exc.value.new_price == 1000_00


async def test_archived_product_cannot_be_bought(sm):
    await make_user(sm, 14, balance=5000_00)
    product = await make_product(sm, is_archived=True)
    with pytest.raises(ProductUnavailable):
        await orders.purchase(sm, user_id=14, product_id=product.id, expected_price=product.price, nonce="n")


async def test_banned_user_cannot_buy(sm):
    await make_user(sm, 15, balance=5000_00, is_banned=True)
    product = await make_product(sm)
    with pytest.raises(AccessRestricted):
        await orders.purchase(sm, user_id=15, product_id=product.id, expected_price=product.price, nonce="n")


async def test_repeated_confirmation_charges_once(sm):
    await make_user(sm, 16, balance=5000_00)
    product = await make_product(sm, price=1000_00, stock=5)
    first = await orders.purchase(sm, user_id=16, product_id=product.id, expected_price=1000_00, nonce="same")
    second = await orders.purchase(sm, user_id=16, product_id=product.id, expected_price=1000_00, nonce="same")
    assert first.created and not second.created
    assert first.order.id == second.order.id
    assert second.content == first.content
    assert await balance(sm, 16) == 4000_00
    assert await count(sm, select(func.count(Order.id))) == 1


async def test_concurrent_double_tap_charges_once(sm):
    await make_user(sm, 17, balance=5000_00)
    product = await make_product(sm, price=1000_00, stock=5)
    results = await asyncio.gather(
        *[orders.purchase(sm, user_id=17, product_id=product.id, expected_price=1000_00, nonce="tap") for _ in range(8)]
    )
    assert sum(r.created for r in results) == 1
    assert len({r.order.id for r in results}) == 1
    assert await balance(sm, 17) == 4000_00
    assert await count(sm, select(func.count(ProductItem.id)).where(ProductItem.status == ItemStatus.SOLD)) == 1


async def test_last_unit_goes_to_exactly_one_buyer(sm):
    product = await make_product(sm, price=500_00, stock=1)
    buyers = list(range(100, 110))
    for uid in buyers:
        await make_user(sm, uid, balance=1000_00)

    async def attempt(uid: int):
        try:
            return await orders.purchase(sm, user_id=uid, product_id=product.id, expected_price=500_00, nonce=f"n{uid}")
        except OutOfStock:
            return None

    results = await asyncio.gather(*[attempt(uid) for uid in buyers])
    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert await count(sm, select(func.count(Order.id))) == 1
    total = await count(sm, select(func.sum(User.balance)).where(User.id.in_(buyers)))
    assert total == 10 * 1000_00 - 500_00


async def test_no_oversell_under_load(sm):
    product = await make_product(sm, price=100_00, stock=7)
    buyers = list(range(200, 220))
    for uid in buyers:
        await make_user(sm, uid, balance=1000_00)

    async def attempt(uid: int, n: int):
        try:
            return await orders.purchase(sm, user_id=uid, product_id=product.id, expected_price=100_00, nonce=f"{uid}-{n}")
        except OutOfStock:
            return None

    results = await asyncio.gather(*[attempt(uid, n) for uid in buyers for n in range(2)])
    sold = [r for r in results if r is not None]
    assert len(sold) == 7
    assert len({r.order.item_id for r in sold}) == 7
    assert await count(sm, select(func.count(ProductItem.id)).where(ProductItem.status == ItemStatus.AVAILABLE)) == 0


async def test_one_user_parallel_purchases_never_overdraw(sm):
    await make_user(sm, 18, balance=250_00)
    product = await make_product(sm, price=100_00, stock=10)

    async def attempt(n: int):
        try:
            return await orders.purchase(sm, user_id=18, product_id=product.id, expected_price=100_00, nonce=f"p{n}")
        except InsufficientFunds:
            return None

    results = await asyncio.gather(*[attempt(n) for n in range(6)])
    assert sum(r is not None for r in results) == 2
    assert await balance(sm, 18) == 50_00


async def test_refund_returns_money_once_and_revokes_unit(sm):
    await make_user(sm, 19, balance=1000_00)
    product = await make_product(sm, price=600_00, stock=2)
    result = await orders.purchase(sm, user_id=19, product_id=product.id, expected_price=600_00, nonce="r")

    first, second = await asyncio.gather(
        orders.refund_order(sm, result.order.id, ADMIN_ID, "не подошёл"),
        orders.refund_order(sm, result.order.id, ADMIN_ID, "повтор"),
    )
    assert sorted([first.refunded, second.refunded]) == [False, True]
    assert await balance(sm, 19) == 1000_00
    async with sm() as s:
        order = await s.get(Order, result.order.id)
        assert order.status == OrderStatus.REFUNDED and order.refunded_by == ADMIN_ID
        assert (await s.get(ProductItem, order.item_id)).status == ItemStatus.REVOKED


def test_parse_order_number():
    assert orders.parse_order_number("AM-000123") == 123
    assert orders.parse_order_number("#45") == 45
    assert orders.parse_order_number("am12") == 12
    assert orders.parse_order_number("abc") is None
