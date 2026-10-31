"""Источник цен TonAPI на локальном сервере, повторяющем формат ответов tonapi.io."""
from decimal import Decimal

import pytest
from aiohttp import web

from app.nft.tonapi import TonapiGiftSource

REAL, FAKE = "0:real", "0:fake"


def _nft(model, backdrop, price_ton, *, market="Getgems Sales", token="Gram"):
    sale = None
    if price_ton is not None:
        sale = {"market": {"name": market}, "price": {"currency_type": "native", "value": str(int(Decimal(str(price_ton)) * 10**9)),
                                                     "decimals": 9, "token_name": token}}
    return {"metadata": {"attributes": [{"trait_type": "Model", "value": model}, {"trait_type": "Backdrop", "value": backdrop},
                                        {"trait_type": "Symbol", "value": "Star"}]}, "sale": sale}


ITEMS = [_nft("Cozy Galaxy", "Black", 900), _nft("Cozy Galaxy", "Coral Red", 650), _nft("Cozy Galaxy", "Black", 0),
         _nft("Ruby", "Onyx Black", 300), _nft("Ruby", "Black", None)] + [_nft("Filler", "Coral Red", None)] * 100


@pytest.fixture
async def api():
    calls = []

    async def search(request):
        calls.append("search")
        return web.json_response({"addresses": [{"address": FAKE, "name": "Plush Pepes · collection", "trust": "none"},
                                                {"address": REAL, "name": "Plush Pepes · account", "trust": "whitelist"}]})

    async def collection(request):
        calls.append("collection")
        if request.match_info["addr"] != REAL:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"metadata": {"name": "Plush Pepes"}})

    async def items(request):
        calls.append("items")
        offset, limit = int(request.query["offset"]), int(request.query["limit"])
        return web.json_response({"nft_items": ITEMS[offset:offset + limit]})

    app = web.Application()
    app.router.add_get("/v2/accounts/search", search)
    app.router.add_get("/v2/nfts/collections/{addr}", collection)
    app.router.add_get("/v2/nfts/collections/{addr}/items", items)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    src = TonapiGiftSource(base_url=f"http://127.0.0.1:{port}", min_interval=0)
    yield src, calls
    await src.close()
    await runner.cleanup()


async def test_rules_and_whitelisted_collection(api):
    src, calls = api
    q = await src.quote("Plush Pepe", "Cozy Galaxy", "Black")
    assert q.collection == "Plush Pepes" and q.floor == Decimal(900)  # нулевая цена (аукцион) не считается
    assert (await src.quote("Plush Pepe", "cozy galaxy", "Coral Red")).floor == Decimal(650)  # фон не премиальный
    assert (await src.quote("Plush Pepe", "Ruby", "Onyx Black")).floor == Decimal(300)
    assert (await src.quote("Plush Pepe", None, None)).floor == Decimal(300)
    assert calls.count("items") == 2  # 105 NFT → 2 страницы, дальше кэш
    assert await src.gift_collections() == ["Plush Pepes"]


async def test_no_listing_no_price(api):
    src, _ = api
    q = await src.quote("Plush Pepe", "Ruby", "Black")
    assert q.floor is None and "нет листингов" in q.error
    q = await src.quote("Plush Pepe", "Unknown", None)
    assert q.floor is None
    assert "цену не называть" in q.render(Decimal(10), Decimal(20))


async def test_partial_scan_is_disclosed(api):
    src, _ = api
    src.max_items = 100
    q = await src.quote("Plush Pepe", "Cozy Galaxy", None)
    assert "просмотрены первые 100" in q.basis
