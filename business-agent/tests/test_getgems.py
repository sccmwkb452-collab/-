"""Клиент Getgems на локальном сервере, повторяющем формат Public API."""
from decimal import Decimal

import pytest
from aiohttp import web

from app.nft.getgems import GetgemsClient

ADDR = "EQPlushPepe"


def _item(model, backdrop, symbol, price_ton, *, sale_type="FixPriceSale"):
    return {
        "address": f"EQ{model}{backdrop}{price_ton}",
        "attributes": [{"traitType": "Model", "value": model}, {"traitType": "Backdrop", "value": backdrop},
                       {"traitType": "Symbol", "value": symbol}],
        "sale": {"type": sale_type, "currency": "TON", "fullPrice": str(int(Decimal(str(price_ton)) * 10**9))},
    }


@pytest.fixture
async def api():
    state = {"requests": [], "status": 200}
    on_sale = [
        _item("Cozy Galaxy", "Black", "Star", 900),
        _item("Cozy Galaxy", "Onyx Black", "Heart", 1200),
        _item("Cozy Galaxy", "Black", "Heart", 750),  # самый дешёвый Black — символ не важен
        _item("Cozy Galaxy", "Black", "Star", 500, sale_type="Auction"),  # аукцион не считается
        _item("Ruby", "Black", "Star", 300),  # другая модель
    ]

    def check(request):
        state["requests"].append(str(request.rel_url))
        if state["status"] != 200:
            raise web.HTTPUnauthorized()
        assert request.headers["Authorization"] == "KEY"

    async def collections(request):
        check(request)
        return web.json_response({"success": True, "response": {"items": [
            {"name": "Plush Pepe", "address": ADDR}, {"name": "Durov's Cap", "address": "EQCap"}], "cursor": None}})

    async def attributes(request):
        check(request)
        return web.json_response({"success": True, "response": {"attributes": [
            {"traitType": "Model", "values": [
                {"value": "Cozy Galaxy", "count": 10, "minPrice": "650", "minPriceNano": "650000000000"},
                {"value": "Ruby", "count": 5, "minPrice": "300", "minPriceNano": "300000000000"},
                {"value": "Rare One", "count": 1, "minPrice": None, "minPriceNano": None}]},
            {"traitType": "Backdrop", "values": [{"value": "Black", "count": 3}, {"value": "Onyx Black", "count": 1},
                                                 {"value": "Coral Red", "count": 9}]},
        ]}})

    async def listings(request):
        check(request)
        page = request.query.get("after")
        items = on_sale[:3] if page is None else on_sale[3:]
        return web.json_response({"success": True, "response": {"items": items, "cursor": None if page else "p2"}})

    async def offchain(request):
        check(request)
        return web.json_response({"success": True, "response": {"items": [], "cursor": None}})

    app = web.Application()
    app.router.add_get("/v1/gifts/collections", collections)
    app.router.add_get("/v1/collection/attributes/{addr}", attributes)
    app.router.add_get("/v1/nfts/on-sale/{addr}", listings)
    app.router.add_get("/v1/nfts/offchain/on-sale/{addr}", offchain)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    client = GetgemsClient("KEY", base_url=f"http://127.0.0.1:{port}")
    yield client, state
    await client.close()
    await runner.cleanup()


async def test_premium_backdrop_uses_model_and_backdrop_listing(api):
    client, _ = api
    q = await client.quote("Plush Pepe", "Cozy Galaxy", "Black")
    assert q.floor == Decimal(750)
    assert q.basis.startswith("модель + премиальный фон")
    q = await client.quote("Plush Pepe", "cozy galaxy", "onyx black")
    assert q.floor == Decimal(1200)


async def test_regular_backdrop_uses_model_floor(api):
    client, _ = api
    q = await client.quote("Plush Pepe", "Cozy Galaxy", "Coral Red")
    assert q.floor == Decimal(650)
    assert "фон и символ не учитываются" in q.basis


async def test_collection_floor_without_model_and_fuzzy_names(api):
    client, _ = api
    q = await client.quote("Plush Pepe", None, None)
    assert q.floor == Decimal(300)
    q = await client.quote("Plush Pepes", "Cozy Galaxi", None)
    assert q.collection == "Plush Pepe" and q.model == "Cozy Galaxy"


async def test_no_data_is_not_invented(api):
    client, _ = api
    q = await client.quote("Plush Pepe", "Rare One", None)
    assert q.floor is None and q.error
    assert "цену не называть" in q.render(Decimal(10), Decimal(20))
    q = await client.quote("Unknown Gift", None, None)
    assert q.floor is None and "не найдена" in q.error
    q = await client.quote("Plush Pepe", "Ruby", "Onyx Black")
    assert q.floor is None


async def test_render_markup_and_cache(api):
    client, state = api
    q = await client.quote("Plush Pepe", "Cozy Galaxy", None)
    assert "предложение 715–780 TON" in q.render(Decimal(10), Decimal(20))
    before = len(state["requests"])
    await client.quote("Plush Pepe", "Cozy Galaxy", None)
    assert len(state["requests"]) == before


async def test_bad_key(api):
    client, state = api
    state["status"] = 401
    q = await client.quote("Plush Pepe", "Cozy Galaxy", None)
    assert q.floor is None and "ключ Getgems" in q.error
