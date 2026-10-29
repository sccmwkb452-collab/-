from decimal import Decimal

import pytest

from app.ai.state import DealState
from app.core.owners import get_policy
from app.db.models import DealStatus, TradeBotConfig
from app.deals.manager import DealManager
from app.trading.base import Capability, OpResult, OpStatus
from app.trading.guard import TradeBlocked, require_trade_bot, verify_shared_bot
from tests.conftest import FakeAdapter, FakeFactory, add_conversation, add_trade_bot

AGREED = DealState(counterparty_role="seller", item_description="Plush Pepe #7", quantity=1, agreed_price="15",
                   currency="TON", product_type="NFT").dump()


async def test_no_trade_bot_blocks(sessions, owner):
    async with sessions() as s:
        with pytest.raises(TradeBlocked) as e:
            await require_trade_bot(s, owner.id, FakeFactory(FakeAdapter()))
        assert e.value.code == "no_trade_bot"


async def test_unverified_bot_blocks(sessions, owner):
    async with sessions() as s:
        await add_trade_bot(s, owner.id, verified=False)
        with pytest.raises(TradeBlocked) as e:
            await require_trade_bot(s, owner.id, FakeFactory(FakeAdapter()))
        assert e.value.code == "not_verified"


async def test_identity_snapshot_mismatch_blocks(sessions, owner):
    async with sessions() as s:
        await add_trade_bot(s, owner.id)
        with pytest.raises(TradeBlocked) as e:
            await require_trade_bot(s, owner.id, FakeFactory(FakeAdapter()), expected_bot_user_id=42)
        assert e.value.code == "identity_mismatch"


async def test_lookalike_username_for_official_adapter_blocks(sessions, owner):
    async with sessions() as s:
        await add_trade_bot(s, owner.id, username="cryptob0t")
        with pytest.raises(TradeBlocked) as e:
            await require_trade_bot(s, owner.id, FakeFactory(FakeAdapter(official={"cryptobot"})))
        assert e.value.code == "identity_mismatch"


async def test_unavailable_bot_stops_without_fallback(sessions, owner):
    async with sessions() as s:
        await add_trade_bot(s, owner.id)
        await add_trade_bot(s, owner.id, username="other_bot", user_id=77, active=False)
        with pytest.raises(TradeBlocked) as e:
            await require_trade_bot(s, owner.id, FakeFactory(FakeAdapter(available=False)))
        assert e.value.code == "unavailable"


async def test_unsupported_operation_blocks(sessions, owner):
    async with sessions() as s:
        await add_trade_bot(s, owner.id)
        with pytest.raises(TradeBlocked) as e:
            await require_trade_bot(s, owner.id, FakeFactory(FakeAdapter(caps=[Capability.CHECK])), operation=Capability.PAY)
        assert e.value.code == "not_supported"


def test_verify_shared_bot():
    assert verify_shared_bot("cryptopay", 1, "CryptoBot", "cryptobot") is None
    assert verify_shared_bot("cryptopay", 1, "CryptoB0t", "cryptobot")
    assert verify_shared_bot("manual", 1, None, None)


async def _setup_deal(s, owner, adapter, *, budget=Decimal("100")):
    await add_trade_bot(s, owner.id)
    conv = await add_conversation(s, owner.id, state=AGREED)
    policy = await get_policy(s, owner.id)
    policy.daily_budget, policy.budget_currency = budget, "TON"
    mgr = DealManager(FakeFactory(adapter))
    prepared = await mgr.prepare_from_conversation(s, conv)
    return mgr, conv, prepared.deal


async def test_prepare_is_idempotent_and_requires_fields(sessions, owner):
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, FakeAdapter())
        assert deal.status == DealStatus.AWAITING_CONFIRMATION
        again = await mgr.prepare_from_conversation(s, conv)
        assert again.deal.id == deal.id and not again.created_now
        conv.state = {**AGREED, "currency": None}
        missing = await mgr.prepare_from_conversation(s, conv)
        assert missing.deal is None and "валюта" in missing.missing


async def test_create_and_pay_success(sessions, owner):
    adapter = FakeAdapter()
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, adapter)
        step = await mgr.confirm_and_create(s, deal)
        assert deal.status == DealStatus.CREATED, step.message
        step = await mgr.pay(s, deal)
        assert deal.status == DealStatus.PAID
        assert len(adapter.pay_calls) == 1 and deal.payment_spend_id == adapter.pay_calls[0]
        assert deal.funds_committed_at is not None


async def test_unknown_payment_is_never_resent_blindly(sessions, owner):
    adapter = FakeAdapter(pay_results=[OpResult(OpStatus.UNKNOWN, error="timeout")],
                          status_results=[OpResult(OpStatus.NOT_FOUND), OpResult(OpStatus.SUCCESS, external_id="t9")])
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, adapter)
        await mgr.confirm_and_create(s, deal)
        await mgr.pay(s, deal)
        assert deal.status == DealStatus.UNKNOWN
        # Повторное нажатие «Оплатить» = только сверка, без нового платежа.
        step = await mgr.pay(s, deal)
        assert len(adapter.pay_calls) == 1
        assert deal.status == DealStatus.UNKNOWN and "не найден" in step.message
        step = await mgr.reconcile(s, deal)
        assert deal.status == DealStatus.PAID and len(adapter.pay_calls) == 1


async def test_retry_uses_same_spend_id(sessions, owner):
    adapter = FakeAdapter(pay_results=[OpResult(OpStatus.UNKNOWN), OpResult(OpStatus.SUCCESS)],
                          status_results=[OpResult(OpStatus.NOT_FOUND)])
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, adapter)
        await mgr.confirm_and_create(s, deal)
        await mgr.pay(s, deal)
        await mgr.retry_payment_same_spend_id(s, deal)
        assert deal.status == DealStatus.PAID
        assert adapter.pay_calls[0] == adapter.pay_calls[1]


async def test_budget_is_never_exceeded(sessions, owner):
    adapter = FakeAdapter()
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, adapter, budget=Decimal("10"))
        await mgr.confirm_and_create(s, deal)
        if deal.status == DealStatus.CREATED:
            await mgr.pay(s, deal)
        assert deal.status != DealStatus.PAID
        assert adapter.pay_calls == []


async def test_currency_must_be_allowed(sessions, owner):
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, FakeAdapter())
        bot = await s.get(TradeBotConfig, deal.trade_bot_id)
        bot.currencies = ["USDT"]
        step = await mgr.confirm_and_create(s, deal)
        assert step.blocked and any("TON" in p for p in step.problems)


async def test_auto_mode_requires_explicit_enable(sessions, owner):
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, FakeAdapter())
        step = await mgr.confirm_and_create(s, deal, automatic=True)
        assert step.blocked and any("Автоматический режим" in p for p in step.problems)
        policy = await get_policy(s, owner.id)
        policy.auto_mode_enabled, policy.auto_currencies, policy.auto_max_price = True, ["TON"], Decimal("20")
        step = await mgr.confirm_and_create(s, deal, automatic=True)
        assert deal.status == DealStatus.CREATED, step.problems
        step = await mgr.pay(s, deal, automatic=True)
        assert step.blocked and any("Автоматическая оплата" in p for p in step.problems)


async def test_switching_trade_bot_stops_prepared_deal(sessions, owner):
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, FakeAdapter())
        bot = await s.get(TradeBotConfig, deal.trade_bot_id)
        bot.is_active = False
        await add_trade_bot(s, owner.id, username="cryptobot", user_id=123456, active=True)
        step = await mgr.confirm_and_create(s, deal)
        assert step.blocked and "другого торгового бота" in step.message
        assert deal.status == DealStatus.AWAITING_CONFIRMATION


async def test_manual_adapter_requires_human_steps(sessions, owner):
    from app.trading.manual import ManualTradeBotAdapter

    async with sessions() as s:
        await add_trade_bot(s, owner.id, username="garant_bot", user_id=5, adapter="manual")
        conv = await add_conversation(s, owner.id, state=AGREED)
        mgr = DealManager(FakeFactory(ManualTradeBotAdapter("garant_bot")))
        deal = (await mgr.prepare_from_conversation(s, conv)).deal
        await mgr.confirm_and_create(s, deal)
        assert deal.status == DealStatus.USER_ACTION_REQUIRED
        assert "t.me/garant_bot" in deal.item["instructions"]
        await mgr.mark_manual(s, deal, DealStatus.PAID)
        assert deal.status == DealStatus.PAID
        await mgr.mark_manual(s, deal, DealStatus.COMPLETED)
        assert deal.status == DealStatus.COMPLETED


async def test_api_bot_payment_cannot_be_marked_paid_manually(sessions, owner):
    async with sessions() as s:
        mgr, conv, deal = await _setup_deal(s, owner, FakeAdapter())
        await mgr.confirm_and_create(s, deal)
        step = await mgr.mark_manual(s, deal, DealStatus.PAID)
        assert step.blocked and deal.status == DealStatus.CREATED
