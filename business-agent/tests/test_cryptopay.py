import asyncio
from decimal import Decimal

import pytest
from aiohttp import web

from app.trading.base import DealRequest, OpStatus
from app.trading.cryptopay import CryptoPayAdapter

REQ = DealRequest(deal_id=1, side="buy", amount=Decimal("15"), currency="TON", description="Сделка #1",
                  counterparty_telegram_id=555, idempotency_key="k1")


@pytest.fixture
async def server():
    state = {"transfers": [], "mode": "ok", "calls": []}

    async def handler(request: web.Request):
        method = request.match_info["method"]
        if request.headers.get("Crypto-Pay-API-Token") != "tok":
            return web.json_response({"ok": False, "error": {"code": 401, "name": "UNAUTHORIZED"}})
        params = await request.json()
        state["calls"].append((method, params))
        if state["mode"] == "slow":
            await asyncio.sleep(2)
        if state["mode"] == "500":
            return web.Response(status=502)
        if method == "getMe":
            return web.json_response({"ok": True, "result": {"app_id": 1, "name": "test"}})
        if method == "getCurrencies":
            return web.json_response({"ok": True, "result": [{"code": "TON", "is_fiat": False}, {"code": "USD", "is_fiat": True}]})
        if method == "transfer":
            if state["mode"] == "funds":
                return web.json_response({"ok": False, "error": {"code": 400, "name": "INSUFFICIENT_FUNDS"}})
            tr = {"transfer_id": 77, "spend_id": params["spend_id"], "user_id": int(params["user_id"]),
                  "asset": params["asset"], "amount": params["amount"], "status": "completed"}
            state["transfers"].append(tr)
            return web.json_response({"ok": True, "result": tr})
        if method == "getTransfers":
            return web.json_response({"ok": True, "result": {"items": state["transfers"]}})
        if method == "createInvoice":
            url = state.get("invoice_url", "https://t.me/CryptoBot?start=IVabc")
            return web.json_response({"ok": True, "result": {"invoice_id": 5, "status": "active", "bot_invoice_url": url,
                                                             "payload": params.get("payload")}})
        if method == "getInvoices":
            return web.json_response({"ok": True, "result": {"items": [{"invoice_id": 5, "status": state.get("inv", "paid")}]}})
        return web.json_response({"ok": False, "error": {"code": 400, "name": "METHOD_NOT_FOUND"}})

    app = web.Application()
    app.router.add_post("/api/{method}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}", state
    await runner.cleanup()


def adapter(url, timeout=5):
    return CryptoPayAdapter("tok", "mainnet", base_url=url, timeout=timeout)


async def test_check_and_currencies(server):
    url, _ = server
    a = adapter(url)
    res = await a.check()
    assert res.ok and res.currencies == ["TON"]
    await a.close()


async def test_bad_token(server):
    url, _ = server
    a = CryptoPayAdapter("wrong", base_url=url)
    assert not (await a.check()).ok
    await a.close()


async def test_transfer_success_and_status(server):
    url, state = server
    a = adapter(url)
    r = await a.pay(REQ, "spend-1")
    assert r.status == OpStatus.SUCCESS and r.external_id == "77"
    st = await a.payment_status("spend-1", None)
    assert st.status == OpStatus.SUCCESS
    assert (await a.payment_status("spend-other", None)).status == OpStatus.NOT_FOUND
    await a.close()


async def test_transfer_error_is_failed(server):
    url, state = server
    state["mode"] = "funds"
    a = adapter(url)
    r = await a.pay(REQ, "spend-2")
    assert r.status == OpStatus.FAILED and r.error == "INSUFFICIENT_FUNDS"
    await a.close()


async def test_timeout_and_5xx_are_unknown(server):
    url, state = server
    state["mode"] = "slow"
    a = adapter(url, timeout=0.5)
    assert (await a.pay(REQ, "spend-3")).status == OpStatus.UNKNOWN
    await a.close()
    state["mode"] = "500"
    a = adapter(url)
    assert (await a.pay(REQ, "spend-4")).status == OpStatus.UNKNOWN
    await a.close()


async def test_invoice_link_must_point_to_official_bot(server):
    url, state = server
    a = adapter(url)
    sell = DealRequest(**{**REQ.__dict__, "side": "sell"})
    ok = await a.create_invoice(sell)
    assert ok.status == OpStatus.SUCCESS and ok.url.startswith("https://t.me/CryptoBot")
    state["invoice_url"] = "https://t.me/CryptoB0tPay?start=x"
    bad = await a.create_invoice(sell)
    assert bad.status == OpStatus.FAILED
    assert (await a.deal_status("5")).status == OpStatus.SUCCESS
    await a.close()
