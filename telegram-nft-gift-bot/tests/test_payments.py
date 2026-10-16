from __future__ import annotations

import base64
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from nft_gift_bot.models import Payment, PaymentStatus
from nft_gift_bot.payments.ton import format_ton, new_memo, ton_to_nano, ton_transfer_link
from nft_gift_bot.payments.toncenter import ChainUnavailableError, parse_transactions
from nft_gift_bot.payments.verifier import IncomingTransfer, find_payment_transfer
from nft_gift_bot.services.payment_service import PaymentService
from nft_gift_bot.services.subscription_service import SubscriptionService
from tests.conftest import NOW, FakeChain, make_user

TEN_TON = 10 * 10**9
ADDR = "UQ-test-receiver"


def tx(memo: str, value: int = TEN_TON, tx_hash: str = "h1", utime: int | None = None) -> IncomingTransfer:
    return IncomingTransfer(tx_hash=tx_hash, sender="0:sender", value_nano=value, comment=memo,
                            utime=utime if utime is not None else int(NOW.timestamp()) + 10)


def test_ton_amounts() -> None:
    assert ton_to_nano(Decimal("10")) == TEN_TON
    assert ton_to_nano("0.5") == 500_000_000
    assert format_ton(TEN_TON) == "10"
    assert format_ton(1_500_000_000) == "1.5"
    for bad in ("0", "-1", "abc", "0.0000000001"):
        with pytest.raises(ValueError):
            ton_to_nano(bad)


def test_memo_unique_and_link() -> None:
    memos = {new_memo() for _ in range(500)}
    assert len(memos) == 500
    assert all(m.startswith("NFT-") for m in memos)
    assert ton_transfer_link("ADDR", 5, "NFT-AB") == "ton://transfer/ADDR?amount=5&text=NFT-AB"


def test_verifier_requires_memo_amount_and_unused_hash() -> None:
    transfers = [tx("NFT-OTHER", tx_hash="a"), tx("NFT-X", value=TEN_TON - 1, tx_hash="b"), tx("NFT-X", tx_hash="c")]
    assert find_payment_transfer(transfers, "NFT-X", TEN_TON).tx_hash == "c"
    assert find_payment_transfer(transfers, "NFT-X", TEN_TON, used_hashes={"c"}) is None
    assert find_payment_transfer(transfers, "NFT-NONE", TEN_TON) is None


def test_parse_toncenter_payload() -> None:
    payload = {
        "ok": True,
        "result": [
            {"transaction_id": {"hash": "H1"}, "utime": 100,
             "in_msg": {"source": "EQsender", "value": "10000000000", "message": "NFT-ABC"}},
            {"transaction_id": {"hash": "H2"}, "utime": 101,
             "in_msg": {"source": "EQsender", "value": "1",
                        "msg_data": {"@type": "msg.dataText", "text": base64.b64encode(b"NFT-B64").decode()}}},
            {"transaction_id": {"hash": "H3"}, "in_msg": {"source": "", "value": "0"}},  # external
        ],
    }
    parsed = parse_transactions(payload)
    assert [(p.tx_hash, p.comment, p.value_nano) for p in parsed] == [("H1", "NFT-ABC", TEN_TON), ("H2", "NFT-B64", 1)]
    with pytest.raises(ChainUnavailableError):
        parse_transactions({"ok": False, "error": "rate limit"})


async def _invoice(session, user, now=NOW) -> Payment:
    return await PaymentService(session).create_subscription_invoice(user.id, TEN_TON, 30, timedelta(minutes=30), now)


async def test_invoice_reused_while_open(session) -> None:
    user = await make_user(session)
    first = await _invoice(session, user)
    second = await _invoice(session, user)
    assert first.id == second.id
    assert first.status == PaymentStatus.PENDING


async def test_payment_activates_subscription_only_after_onchain_match(session) -> None:
    user = await make_user(session)
    payment = await _invoice(session, user)
    service = PaymentService(session)

    chain = FakeChain([tx("NFT-WRONG")])
    assert await service.process_pending(chain, ADDR, NOW) == []
    assert not await SubscriptionService(session).is_active(user.id, NOW)

    chain.transfers.append(tx(payment.memo, tx_hash="good"))
    confirmed = await service.process_pending(chain, ADDR, NOW)
    assert [c.tx_hash for c in confirmed] == ["good"]
    await session.refresh(payment)
    assert payment.status == PaymentStatus.PAID
    assert await SubscriptionService(session).is_active(user.id, NOW)
    sub = await SubscriptionService(session).get(user.id)
    assert sub.expires_at == NOW + timedelta(days=30)


async def test_same_payment_never_processed_twice(session) -> None:
    user = await make_user(session)
    payment = await _invoice(session, user)
    chain = FakeChain([tx(payment.memo, tx_hash="once")])
    service = PaymentService(session)
    assert len(await service.process_pending(chain, ADDR, NOW)) == 1
    assert await service.process_pending(chain, ADDR, NOW) == []
    sub = await SubscriptionService(session).get(user.id)
    assert sub.expires_at == NOW + timedelta(days=30)  # not extended twice


async def test_tx_hash_cannot_confirm_two_invoices(session) -> None:
    alice = await make_user(session, 1)
    bob = await make_user(session, 2)
    p1 = await _invoice(session, alice)
    p2 = await _invoice(session, bob)
    # Forged scenario: one transaction hash reused with a different memo.
    chain = FakeChain([tx(p1.memo, tx_hash="dup"), tx(p2.memo, tx_hash="dup")])
    confirmed = await PaymentService(session).process_pending(chain, ADDR, NOW)
    assert len(confirmed) == 1
    with pytest.raises(IntegrityError):
        session.add(Payment(user_id=bob.id, amount_nano=1, subscription_days=1, memo="NFT-Z", ton_tx_hash="dup",
                            expires_at=NOW))
        await session.flush()


async def test_underpayment_and_old_transactions_ignored(session) -> None:
    user = await make_user(session)
    payment = await _invoice(session, user)
    old = tx(payment.memo, tx_hash="old", utime=int(NOW.timestamp()) - 3600)
    small = tx(payment.memo, value=TEN_TON // 2, tx_hash="small")
    assert await PaymentService(session).process_pending(FakeChain([old, small]), ADDR, NOW) == []


async def test_stale_invoice_expires(session) -> None:
    user = await make_user(session)
    payment = await _invoice(session, user)
    await PaymentService(session).process_pending(FakeChain(), ADDR, NOW + timedelta(days=2))
    await session.refresh(payment)
    assert payment.status == PaymentStatus.EXPIRED


async def test_cancel_only_own_pending_invoice(session) -> None:
    owner = await make_user(session, 1)
    stranger = await make_user(session, 2)
    payment = await _invoice(session, owner)
    service = PaymentService(session)
    assert not await service.cancel(payment.id, stranger.id)
    assert await service.cancel(payment.id, owner.id)
    assert not await service.cancel(payment.id, owner.id)
