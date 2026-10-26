"""Supplier adapters against recorded/contract responses (httpx.MockTransport),
FX parsing, Fragment page parsing, PlayerOK manual mode."""

from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

import httpx
import pytest

from autocommerce.database.enums import SupplierOrderStatus
from autocommerce.integrations.fx import cbr
from autocommerce.integrations.http import IntegrationError, with_retries
from autocommerce.integrations.marketplace.playerok_manual import PlayerokManualAdapter
from autocommerce.integrations.suppliers.base import PurchaseRequest
from autocommerce.integrations.suppliers.fragment import FragmentAdapter, parse_premium, parse_stars
from autocommerce.integrations.suppliers.reloadly import ReloadlyAdapter, _token_cache
from autocommerce.integrations.suppliers.smm_v2 import SmmV2Adapter

from .conftest import mock_http

FIXTURES = Path(__file__).parent / "fixtures"


def test_fragment_pages_are_parsed():
    stars = parse_stars((FIXTURES / "fragment_stars.html").read_text())
    premium = parse_premium((FIXTURES / "fragment_premium.html").read_text())
    assert len(stars) >= 20 and stars[0].external_id == "stars:50"
    assert stars[0].currency == "USD" and stars[0].price == D("0.75")
    assert stars[0].raw["price_ton"]
    assert {p.external_id for p in premium} == {"premium:3", "premium:6", "premium:12"}
    assert next(p for p in premium if p.external_id == "premium:12").price == D("28.99")


async def test_fragment_layout_change_is_reported():
    mock_http(lambda request: httpx.Response(200, text="<html>redesigned</html>"))
    check = await FragmentAdapter().check()
    assert not check.ok and "вёрстка" in check.message
    with pytest.raises(IntegrationError):
        await FragmentAdapter().fetch_catalog()


async def test_fragment_never_buys():
    from autocommerce.integrations.suppliers.base import PurchaseNotSupported

    with pytest.raises(PurchaseNotSupported):
        await FragmentAdapter().purchase(PurchaseRequest("k", "stars:50", 1))


def test_cbr_xml_parsing():
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?><ValCurs Date="24.10.2026" name="Foreign Currency Market">'
        '<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal><Name>Dollar</Name><Value>80,5381</Value></Valute>'
        '<Valute ID="R01375"><NumCode>156</NumCode><CharCode>KZT</CharCode><Nominal>100</Nominal><Name>Tenge</Name><Value>15,1200</Value></Valute>'
        "</ValCurs>"
    ).encode("cp1251")
    rates = cbr.parse(xml)
    assert rates.rates["USD"].rate == D("80.5381")
    assert rates.rates["KZT"].rate == D("0.1512")  # per one unit, nominal 100
    with pytest.raises(IntegrationError):
        cbr.parse(b"<html>not xml")


async def test_retries_only_transient_errors():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise IntegrationError("busy", transient=True)
        return "ok"

    async def no_sleep(_):
        return None

    assert await with_retries(flaky, sleep=no_sleep) == "ok" and calls["n"] == 3

    async def fatal():
        raise IntegrationError("bad key")

    with pytest.raises(IntegrationError):
        await with_retries(fatal, sleep=no_sleep)


def smm_handler(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        state.setdefault("calls", []).append(form)
        if form.get("key") != "good":
            return httpx.Response(200, json={"error": "Invalid API key"})
        action = form["action"]
        if action == "balance":
            return httpx.Response(200, json={"balance": "1520.50", "currency": "RUB"})
        if action == "services":
            return httpx.Response(
                200,
                json=[
                    {
                        "service": 11,
                        "name": "Подписчики Telegram",
                        "type": "Default",
                        "category": "Telegram",
                        "rate": "95.5",
                        "min": "100",
                        "max": "50000",
                    }
                ],
            )
        if action == "add":
            if state.get("timeout"):
                raise httpx.ReadTimeout("timeout", request=request)
            return httpx.Response(200, json={"order": 777})
        if action == "status":
            return httpx.Response(200, json={"charge": "95.5", "status": "Completed", "remains": "0", "currency": "RUB"})
        return httpx.Response(400, json={"error": "unknown"})

    return handler


async def test_smm_panel_contract():
    state: dict = {}
    mock_http(smm_handler(state))
    bad = await SmmV2Adapter({"api_key": "nope"}).check()
    assert not bad.ok and "Invalid API key" in bad.message
    adapter = SmmV2Adapter({"api_key": "good"})
    check = await adapter.check()
    assert check.ok and check.balance == D("1520.50")
    items = await adapter.fetch_catalog()
    assert items[0].price == D("95.5") and items[0].price_unit == 1000 and items[0].min_quantity == 100
    placed = await adapter.purchase(PurchaseRequest("k1", "11", 1000, buyer_data={"link": "https://t.me/channel"}))
    assert placed.status is SupplierOrderStatus.PENDING and placed.external_id == "777"
    status = await adapter.order_status("777")
    assert status.status is SupplierOrderStatus.SUCCEEDED and status.cost == D("95.5")


async def test_smm_purchase_timeout_is_unknown_not_retried():
    state = {"timeout": True}
    mock_http(smm_handler(state))
    result = await SmmV2Adapter({"api_key": "good"}).purchase(PurchaseRequest("k1", "11", 1000, buyer_data={"link": "https://t.me/x"}))
    assert result.status is SupplierOrderStatus.UNKNOWN
    assert sum(1 for c in state["calls"] if c["action"] == "add") == 1  # never retried automatically


async def test_smm_purchase_requires_buyer_link():
    mock_http(smm_handler({}))
    result = await SmmV2Adapter({"api_key": "good"}).purchase(PurchaseRequest("k1", "11", 1000, buyer_data={}))
    assert result.status is SupplierOrderStatus.FAILED


def reloadly_handler(state: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        state.setdefault("paths", []).append((request.method, path, request.url.params.get("customIdentifier")))
        if request.url.host == "auth.reloadly.com":
            body = json.loads(request.content)
            if body["client_secret"] != "s3cret":
                return httpx.Response(401, json={"message": "invalid"})
            assert body["audience"] == "https://giftcards-sandbox.reloadly.com"
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["Accept"] == "application/com.reloadly.giftcards-v1+json"
        if path == "/accounts/balance":
            return httpx.Response(200, json={"balance": 250.75, "currencyCode": "USD"})
        if path == "/products":
            return httpx.Response(
                200,
                json={
                    "totalPages": 1,
                    "content": [
                        {
                            "productId": 5,
                            "productName": "Steam US",
                            "denominationType": "FIXED",
                            "recipientCurrencyCode": "USD",
                            "senderCurrencyCode": "USD",
                            "fixedRecipientDenominations": [5, 10],
                            "fixedSenderDenominations": [5.0, 10.0],
                            "senderFee": 0.5,
                            "discountPercentage": 2,
                            "country": {"isoName": "US"},
                            "brand": {"brandName": "Steam"},
                        }
                    ],
                },
            )
        if path == "/orders":
            body = request.content.decode()
            assert '"unitPrice": 10' in body and '"customIdentifier": "oi:1:a1"' in body
            if state.get("timeout"):
                raise httpx.ReadTimeout("timeout", request=request)
            return httpx.Response(200, json={"transactionId": 99, "status": "SUCCESSFUL", "amount": 10.3, "currencyCode": "USD"})
        if path == "/orders/transactions/99/cards":
            return httpx.Response(200, json=[{"cardNumber": "ABCD-EFGH-IJKL", "pinCode": "1234"}])
        if path == "/reports/transactions":
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"transactionId": 99, "status": "SUCCESSFUL", "amount": 10.3, "currencyCode": "USD", "customIdentifier": "oi:1:a1"}
                    ]
                },
            )
        return httpx.Response(404)

    return handler


async def test_reloadly_contract_and_codes():
    _token_cache.clear()
    state: dict = {}
    mock_http(reloadly_handler(state))
    bad = await ReloadlyAdapter({"client_id": "id", "client_secret": "wrong"}, {"sandbox": True}).check()
    assert not bad.ok
    _token_cache.clear()
    adapter = ReloadlyAdapter({"client_id": "id", "client_secret": "s3cret"}, {"sandbox": True, "country_code": "US"})
    check = await adapter.check()
    assert check.ok and check.balance == D("250.75") and "песочница" in check.message
    items = await adapter.fetch_catalog()
    assert [i.external_id for i in items] == ["5:5", "5:10"]
    assert items[1].price == D("10.0") * D("98") / D("100") + D("0.5")  # discount and sender fee
    result = await adapter.purchase(PurchaseRequest("oi:1:a1", "5:10", 1))
    assert result.status is SupplierOrderStatus.SUCCEEDED and result.codes == ["ABCD-EFGH-IJKL / PIN 1234"]


async def test_reloadly_unclear_answer_is_reconciled_by_key():
    _token_cache.clear()
    state = {"timeout": True}
    mock_http(reloadly_handler(state))
    adapter = ReloadlyAdapter({"client_id": "id", "client_secret": "s3cret"}, {"sandbox": True, "country_code": "US"})
    result = await adapter.purchase(PurchaseRequest("oi:1:a1", "5:10", 1))
    assert result.status is SupplierOrderStatus.UNKNOWN
    found = await adapter.find_by_key("oi:1:a1")
    assert found is not None and found.status is SupplierOrderStatus.SUCCEEDED and found.codes


async def test_playerok_manual_adapter_is_honest():
    adapter = PlayerokManualAdapter()
    assert not any(adapter.capabilities.as_dict().values())
    for capability in ("fetch_orders", "send_messages", "publish_listings", "raise_listings", "confirm_deals"):
        assert adapter.reason(capability)
    from autocommerce.integrations.marketplace.base import MarketplaceUnavailable

    with pytest.raises(MarketplaceUnavailable):
        await adapter.fetch_orders(None)
    with pytest.raises(MarketplaceUnavailable):
        await adapter.send_message("chat", "text")
