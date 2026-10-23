"""Crypto Pay adapter against a mocked API (no network)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import httpx
from sqlalchemy import select

from starshop.config import get_settings
from starshop.database.enums import OrderStatus, PaymentStatus
from starshop.database.models import Order, Payment
from starshop.payments.cryptopay import SIGNATURE_HEADER, CryptoPayProvider
from starshop.payments.registry import override_provider
from tests.conftest import create_order, tma

TOKEN = "1234:AAcryptopaytesttoken"


class FakeCryptoPay:
    def __init__(self):
        self.invoices: dict[int, dict] = {}
        self.calls: list[tuple[str, dict, dict]] = []
        self.fail_with: int | None = None
        self.connect_error = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.connect_error:
            raise httpx.ConnectError("refused", request=request)
        method = request.url.path.rsplit("/", 1)[-1]
        params = json.loads(request.content or b"{}")
        self.calls.append((method, params, dict(request.headers)))
        if self.fail_with:
            return httpx.Response(self.fail_with, json={"ok": False, "error": {"code": self.fail_with, "name": "INTERNAL"}})
        if method == "createInvoice":
            invoice_id = 1000 + len(self.invoices)
            inv = {
                "invoice_id": invoice_id,
                "hash": "IVabc",
                "currency_type": "fiat",
                "fiat": params["fiat"],
                "amount": params["amount"],
                "status": "active",
                "payload": params["payload"],
                "mini_app_invoice_url": f"https://t.me/CryptoTestnetBot/app?startapp=invoice-IV{invoice_id}",
                "bot_invoice_url": f"https://t.me/CryptoTestnetBot?start=IV{invoice_id}",
            }
            self.invoices[invoice_id] = inv
            return httpx.Response(200, json={"ok": True, "result": inv})
        if method == "getInvoices":
            ids = [int(i) for i in str(params["invoice_ids"]).split(",")]
            return httpx.Response(200, json={"ok": True, "result": {"items": [self.invoices[i] for i in ids if i in self.invoices]}})
        if method == "transfer":
            return httpx.Response(
                200, json={"ok": True, "result": {"transfer_id": 77, "spend_id": params["spend_id"], "status": "completed"}}
            )
        if method == "deleteInvoice":
            return httpx.Response(200, json={"ok": True, "result": True})
        if method == "getBalance":
            return httpx.Response(200, json={"ok": True, "result": [{"currency_code": "USDT", "available": "12.5", "onhold": "0"}]})
        return httpx.Response(404, json={"ok": False, "error": {"name": "METHOD_NOT_FOUND"}})

    def pay(self, invoice_id: int, asset: str = "USDT", amount: str = "1.85") -> None:
        self.invoices[invoice_id].update({"status": "paid", "paid_asset": asset, "paid_amount": amount, "paid_at": "2026-10-23T10:00:00Z"})


def install(fake: FakeCryptoPay) -> CryptoPayProvider:
    provider = CryptoPayProvider(get_settings(), transport=httpx.MockTransport(fake.handler))
    override_provider(provider)
    return provider


def sign(body: bytes) -> str:
    return hmac.new(hashlib.sha256(TOKEN.encode()).digest(), body, hashlib.sha256).hexdigest()


async def test_invoice_is_created_in_shop_currency(client, product):
    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, provider="cryptopay")
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    assert r.status_code == 200, r.text
    pay = r.json()
    assert pay["pay_url"].startswith("https://t.me/")
    assert pay["pay_url_kind"] == "telegram"
    method, params, headers = fake.calls[0]
    assert method == "createInvoice"
    assert params["currency_type"] == "fiat" and params["fiat"] == "RUB" and params["amount"] == "169.00"
    assert params["payload"] == pay["id"]
    assert headers["crypto-pay-api-token"] == TOKEN
    assert params["paid_btn_url"].startswith("https://t.me/pulsar_test_bot")


async def test_signed_webhook_confirms_after_api_verification(client, session, product):
    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, provider="cryptopay")
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    invoice_id = next(iter(fake.invoices))
    fake.pay(invoice_id)
    body = json.dumps(
        {"update_id": 5001, "update_type": "invoice_paid", "request_date": "2026-10-23T10:00:01Z", "payload": fake.invoices[invoice_id]}
    ).encode()
    bad = await client.post("/api/v1/webhooks/payments/cryptopay", content=body, headers={SIGNATURE_HEADER: sign(body + b"x")})
    assert bad.status_code == 401
    ok = await client.post("/api/v1/webhooks/payments/cryptopay", content=body, headers={SIGNATURE_HEADER: sign(body)})
    assert ok.json()["result"] == "confirmed"
    assert any(c[0] == "getInvoices" for c in fake.calls)  # re-read from the API
    await session.commit()
    payment = (await session.execute(select(Payment))).scalar_one()
    assert payment.status == PaymentStatus.succeeded
    assert payment.paid_asset == "USDT" and payment.paid_amount == "1.85"


async def test_forged_paid_status_in_signed_body_is_double_checked(client, session, product):
    """Even a correctly signed body is re-verified against the API."""
    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, provider="cryptopay")
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    invoice_id = next(iter(fake.invoices))
    claimed = {**fake.invoices[invoice_id], "status": "paid"}  # API still says "active"
    body = json.dumps({"update_id": 5002, "update_type": "invoice_paid", "payload": claimed}).encode()
    r = await client.post("/api/v1/webhooks/payments/cryptopay", content=body, headers={SIGNATURE_HEADER: sign(body)})
    assert r.json()["result"] == "noop"
    await session.commit()
    assert (await session.execute(select(Order))).scalar_one().status == OrderStatus.pending_payment


async def test_reconcile_picks_up_missed_webhook(client, session, product):
    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, provider="cryptopay")
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    fake.pay(next(iter(fake.invoices)))
    r = await client.post(f"/api/v1/orders/{order['id']}/check-payment", headers=tma())
    assert r.json()["result"] == "confirmed"
    assert r.json()["order"]["status"] == "paid"


async def test_provider_outage_on_create(client, session, product):
    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, provider="cryptopay")
    fake.fail_with = 500
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "payment_provider_error"
    fake.fail_with = None
    fake.connect_error = True
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    assert r.status_code == 502
    await session.commit()
    pays = (await session.execute(select(Payment))).scalars().all()
    assert {p.status for p in pays} == {PaymentStatus.failed}
    assert (await session.get(Order, uuid.UUID(order["id"]))).status == OrderStatus.created
    # recovery
    fake.connect_error = False
    r = await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    assert r.status_code == 200


async def test_refund_uses_idempotent_transfer(client, session, product):
    fake = FakeCryptoPay()
    install(fake)
    order = await create_order(client, product.id, provider="cryptopay")
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "cryptopay"}, headers=tma())
    fake.pay(next(iter(fake.invoices)))
    await client.post(f"/api/v1/orders/{order['id']}/check-payment", headers=tma())
    from tests.conftest import admin_client

    csrf = await admin_client(client, session)
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/refund", json={"reason": "customer request"}, headers=csrf)
    assert r.status_code == 200, r.text
    from starshop.worker.main import refund_tick

    await refund_tick()
    transfer = next(c for c in fake.calls if c[0] == "transfer")
    payment = (await session.execute(select(Payment))).scalar_one()
    assert transfer[1]["spend_id"] == f"refund-{payment.id.hex}"
    assert transfer[1]["asset"] == "USDT" and transfer[1]["amount"] == "1.85"
    assert transfer[1]["user_id"] == 100001
    await session.commit()
    assert (await session.get(Order, uuid.UUID(order["id"]))).status == OrderStatus.refunded
