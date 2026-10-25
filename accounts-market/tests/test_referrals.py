from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from database.models import Transaction, TxKind, User
from orders import service as orders
from referrals import service as referrals
from services import shop_settings, users
from services.ledger import change_balance
from tests.conftest import make_product, make_user


async def test_link_format():
    user = User(id=5, ref_code="abc123")
    assert referrals.referral_link("my_shop_bot", user) == "https://t.me/my_shop_bot?start=ref_abc123"
    assert referrals.parse_start_arg("ref_abc123") == "abc123"
    assert referrals.parse_start_arg("ref_../x") is None
    assert referrals.parse_start_arg("other") is None


async def test_new_user_is_attached_once(sm):
    await make_user(sm, 50)
    async with sm() as s:
        user, created = await users.get_or_create(s, 51, "new", "New")
        assert created
        referrer = await referrals.attach_referrer(s, user, "code50", is_new=created)
        assert referrer.id == 50
        await s.commit()
    async with sm() as s:
        user, created = await users.get_or_create(s, 51, "new", "New")
        assert not created and user.referrer_id == 50


async def test_existing_user_cannot_be_reassigned(sm):
    await make_user(sm, 52)
    await make_user(sm, 53)
    async with sm() as s:
        user = await s.get(User, 53)
        assert await referrals.attach_referrer(s, user, "code52", is_new=False) is None
        assert user.referrer_id is None


async def test_self_referral_is_impossible(sm):
    async with sm() as s:
        user, created = await users.get_or_create(s, 54, "me", "Me")
        assert await referrals.attach_referrer(s, user, user.ref_code, is_new=True) is None
        assert user.referrer_id is None
    async with sm() as s:  # the database refuses it too
        user = await s.get(User, 54) or User(id=54, ref_code="x54")
        s.add(user)
        user.referrer_id = 54
        with pytest.raises(IntegrityError):
            await s.flush()


async def test_reward_for_every_purchase(sm):
    await make_user(sm, 60)
    await make_user(sm, 61, balance=10_000_00, referrer_id=60)
    product = await make_product(sm, price=1000_00, stock=5)
    for n in range(2):
        result = await orders.purchase(sm, user_id=61, product_id=product.id, expected_price=1000_00, nonce=f"r{n}")
        assert result.referral_tx.amount == 50_00  # default 5%
    async with sm() as s:
        assert (await s.get(User, 60)).balance == 100_00
        stats = await users.profile_stats(s, 60)
        assert (stats.referrals, stats.referrals_with_purchases, stats.referral_earned) == (1, 1, 100_00)
        rows, total = await referrals.reward_history(s, 60, 10, 0)
        assert total == 2 and rows[0].amount == 50_00


async def test_reward_only_for_first_purchase(sm):
    async with sm() as s:
        await shop_settings.save(s, "referral_mode", "first")
        await shop_settings.save(s, "referral_percent", "10")
        await s.commit()
    await make_user(sm, 62)
    await make_user(sm, 63, balance=10_000_00, referrer_id=62)
    product = await make_product(sm, price=1000_00, stock=5)
    first = await orders.purchase(sm, user_id=63, product_id=product.id, expected_price=1000_00, nonce="a")
    second = await orders.purchase(sm, user_id=63, product_id=product.id, expected_price=1000_00, nonce="b")
    assert first.referral_tx.amount == 100_00
    assert second.referral_tx is None


async def test_zero_percent_disables_rewards(sm):
    async with sm() as s:
        await shop_settings.save(s, "referral_percent", "0")
        await s.commit()
    await make_user(sm, 64)
    await make_user(sm, 65, balance=10_000_00, referrer_id=64)
    product = await make_product(sm, price=1000_00)
    result = await orders.purchase(sm, user_id=65, product_id=product.id, expected_price=1000_00, nonce="z")
    assert result.referral_tx is None


async def test_reward_cannot_be_paid_twice_for_one_order(sm):
    await make_user(sm, 66)
    await make_user(sm, 67, balance=10_000_00, referrer_id=66)
    product = await make_product(sm, price=1000_00)
    result = await orders.purchase(sm, user_id=67, product_id=product.id, expected_price=1000_00, nonce="d")
    async with sm() as s:
        with pytest.raises(IntegrityError):
            await change_balance(s, 66, 50_00, TxKind.REFERRAL, order_id=result.order.id)
            await s.flush()
    async with sm() as s:
        assert await s.scalar(select(func.count(Transaction.id)).where(Transaction.kind == TxKind.REFERRAL)) == 1
