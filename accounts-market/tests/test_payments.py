from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import func, select

from database.models import Payment, PaymentStatus, Transaction, TxKind, User
from payments.base import Invoice, InvoiceRequest, PaymentProvider, ProviderError, ProviderStatus
from payments.cryptopay import CryptoPayProvider
from payments.demo import DemoProvider
from payments.service import PaymentService
from payments.webhooks import build_app
from services.errors import ShopError
from tests.conftest import ADMIN_ID, make_user


class FakeProvider(PaymentProvider):
    """Stands in for a real provider API; tests control what it reports."""

    name = "fake"
    title = "Fake"
    supports_refund = True

    def __init__(self) -> None:
        self.states: dict[str, ProviderStatus] = {}
        self.fail_create = False
        self.refunds: list[str] = []

    async def create_invoice(self, request: InvoiceRequest) -> Invoice:
        if self.fail_create:
            raise ProviderError("down")
        ext = f"ext-{request.uid}"
        self.states[ext] = ProviderStatus("pending", request.amount, "RUB")
        return Invoice(ext, f"https://pay.example/{ext}")

    async def fetch_status(self, external_id: str) -> ProviderStatus:
        return self.states[external_id]

    async def parse_webhook(self, body, headers):
        if headers.get("X-Secret") != "ok":
            raise ProviderError("bad signature")
        return json.loads(body)["id"]

    async def refund(self, external_id: str, amount: int) -> None:
        self.refunds.append(external_id)


async def user_balance(sm, uid: int) -> int:
    async with sm() as s:
        return (await s.get(User, uid)).balance


async def topups(sm) -> int:
    async with sm() as s:
        return int(await s.scalar(select(func.count(Transaction.id)).where(Transaction.kind == TxKind.TOPUP)))


async def test_payment_is_not_credited_until_provider_confirms(sm):
    await make_user(sm, 30)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    payment = await service.create(30, 500_00, 100_00, "Shop")
    assert payment.pay_url and payment.status == PaymentStatus.PENDING

    result = await service.check(payment.id)
    assert not result.credited and result.payment.status == PaymentStatus.PENDING
    assert await user_balance(sm, 30) == 0

    provider.states[payment.external_id] = ProviderStatus("paid", 500_00, "RUB")
    notified = []

    async def on_paid(p):
        notified.append(p.id)

    service.on_paid = on_paid
    assert (await service.check(payment.id)).credited
    assert not (await service.check(payment.id)).credited  # second check: no double credit
    assert await user_balance(sm, 30) == 500_00
    assert notified == [payment.id]


async def test_concurrent_checks_credit_once(sm):
    await make_user(sm, 31)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    payment = await service.create(31, 1000_00, 100_00, "Shop")
    provider.states[payment.external_id] = ProviderStatus("paid", 1000_00, "RUB")
    results = await asyncio.gather(*[service.check(payment.id) for _ in range(10)])
    assert sum(r.credited for r in results) == 1
    assert await user_balance(sm, 31) == 1000_00
    assert await topups(sm) == 1


async def test_amount_mismatch_is_not_credited(sm):
    await make_user(sm, 32)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    payment = await service.create(32, 1000_00, 100_00, "Shop")
    provider.states[payment.external_id] = ProviderStatus("paid", 10_00, "RUB")
    assert not (await service.check(payment.id)).credited
    assert await user_balance(sm, 32) == 0
    async with sm() as s:
        assert "mismatch" in (await s.get(Payment, payment.id)).last_error


async def test_minimum_and_maximum(sm):
    await make_user(sm, 33)
    service = PaymentService(sm, FakeProvider(), max_amount=10_000_00)
    with pytest.raises(ShopError):
        await service.create(33, 50_00, 100_00, "Shop")
    with pytest.raises(ShopError):
        await service.create(33, 20_000_00, 100_00, "Shop")


async def test_provider_failure_marks_payment_failed(sm):
    await make_user(sm, 34)
    provider = FakeProvider()
    provider.fail_create = True
    service = PaymentService(sm, provider)
    with pytest.raises(ShopError):
        await service.create(34, 500_00, 100_00, "Shop")
    async with sm() as s:
        payment = await s.scalar(select(Payment))
        assert payment.status == PaymentStatus.FAILED and payment.last_error


async def test_expired_invoice_paid_late_is_still_credited(sm):
    await make_user(sm, 35)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    payment = await service.create(35, 300_00, 100_00, "Shop")
    async with sm() as s, s.begin():
        (await s.get(Payment, payment.id)).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert (await service.check(payment.id)).payment.status == PaymentStatus.EXPIRED
    provider.states[payment.external_id] = ProviderStatus("paid", 300_00, "RUB")
    assert (await service.check(payment.id)).credited


async def test_poller_credits_paid_invoices(sm):
    await make_user(sm, 36)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    p1 = await service.create(36, 200_00, 100_00, "Shop")
    await service.create(36, 300_00, 100_00, "Shop")
    provider.states[p1.external_id] = ProviderStatus("paid", 200_00, "RUB")
    assert await service.poll_pending() == 1
    assert await user_balance(sm, 36) == 200_00


async def test_demo_provider_flow(sm):
    await make_user(sm, 37)
    await make_user(sm, 38)
    service = PaymentService(sm, DemoProvider())
    payment = await service.create(37, 500_00, 100_00, "Shop")
    assert not (await service.check(payment.id)).credited
    with pytest.raises(ShopError):  # someone else's invoice
        await service.demo_confirm(payment.id, 38)
    assert (await service.demo_confirm(payment.id, 37)).credited
    assert not (await service.demo_confirm(payment.id, 37)).credited
    assert await user_balance(sm, 37) == 500_00


async def test_demo_confirm_refused_for_real_provider(sm):
    await make_user(sm, 39)
    service = PaymentService(sm, FakeProvider())
    payment = await service.create(39, 500_00, 100_00, "Shop")
    with pytest.raises(ShopError):
        await service.demo_confirm(payment.id, 39)


async def test_refund_debits_balance_once(sm):
    await make_user(sm, 40)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    payment = await service.create(40, 700_00, 100_00, "Shop")
    provider.states[payment.external_id] = ProviderStatus("paid", 700_00, "RUB")
    await service.check(payment.id)
    refunded = await service.refund(payment.id, ADMIN_ID, "ошибочный платёж")
    assert refunded.status == PaymentStatus.REFUNDED
    assert await user_balance(sm, 40) == 0
    assert provider.refunds == [payment.external_id]
    with pytest.raises(ShopError):
        await service.refund(payment.id, ADMIN_ID, "again")


async def test_refund_impossible_when_money_spent(sm):
    await make_user(sm, 41)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    payment = await service.create(41, 700_00, 100_00, "Shop")
    provider.states[payment.external_id] = ProviderStatus("paid", 700_00, "RUB")
    await service.check(payment.id)
    async with sm() as s, s.begin():
        (await s.get(User, 41)).balance = 100_00
    with pytest.raises(ShopError):
        await service.refund(payment.id, ADMIN_ID, "spent")
    async with sm() as s:
        assert (await s.get(Payment, payment.id)).status == PaymentStatus.PAID


async def test_webhook_rejects_forgery_and_rechecks_provider(sm):
    await make_user(sm, 42)
    provider = FakeProvider()
    service = PaymentService(sm, provider)
    payment = await service.create(42, 400_00, 100_00, "Shop")
    async with TestClient(TestServer(build_app(service))) as client:
        forged = await client.post("/payments/fake", data=json.dumps({"id": payment.external_id}))
        assert forged.status == 400
        # Valid notification, but the provider API still says "pending": nothing is credited.
        ok = await client.post("/payments/fake", data=json.dumps({"id": payment.external_id}), headers={"X-Secret": "ok"})
        assert ok.status == 200
        assert await user_balance(sm, 42) == 0
        provider.states[payment.external_id] = ProviderStatus("paid", 400_00, "RUB")
        await client.post("/payments/fake", data=json.dumps({"id": payment.external_id}), headers={"X-Secret": "ok"})
        await client.post("/payments/fake", data=json.dumps({"id": payment.external_id}), headers={"X-Secret": "ok"})
        assert (await client.get("/healthz")).status == 200
    assert await user_balance(sm, 42) == 400_00
    assert await topups(sm) == 1


def test_cryptopay_signature():
    provider = CryptoPayProvider("123:token")
    body = b'{"update_type":"invoice_paid","payload":{"invoice_id":77}}'
    secret = hashlib.sha256(b"123:token").digest()
    good = hmac.new(secret, body, hashlib.sha256).hexdigest()
    assert provider.verify_signature(body, good)
    assert not provider.verify_signature(body, "0" * 64)
    assert not provider.verify_signature(body + b" ", good)


async def test_cryptopay_parse_webhook():
    provider = CryptoPayProvider("123:token")
    body = b'{"update_type":"invoice_paid","payload":{"invoice_id":77}}'
    sig = hmac.new(hashlib.sha256(b"123:token").digest(), body, hashlib.sha256).hexdigest()
    assert await provider.parse_webhook(body, {"crypto-pay-api-signature": sig}) == "77"
    with pytest.raises(ProviderError):
        await provider.parse_webhook(body, {"crypto-pay-api-signature": "bad"})
    status = CryptoPayProvider._status({"status": "paid", "currency_type": "fiat", "fiat": "RUB", "amount": "1490.5"})
    assert status.state == "paid" and status.amount == 1490_50


def test_demo_is_forbidden_in_production(monkeypatch):
    from bot.config import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError):
        Settings()
