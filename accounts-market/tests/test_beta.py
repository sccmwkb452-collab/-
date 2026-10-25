from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from beta.site import USER_ID_BASE, BetaSite
from tests.conftest import make_product

KEY = "beta-test-key-0123456789"


async def test_beta_site_drives_the_real_bot(dispatcher_env, sm):
    dp, _, _ = dispatcher_env
    await make_product(sm, title="Beta item", stock=1)
    site = BetaSite(dp, "1:BETA", KEY)
    app = web.Application()
    site.routes(app)
    async with TestClient(TestServer(app)) as client:
        assert (await client.get("/beta/wrong-key-000000000/")).status == 404
        page = await client.get(f"/beta/{KEY}/")
        assert page.status == 200 and "Shop Beta" in await page.text()

        state = await (await client.get(f"/beta/{KEY}/api/state")).json()
        home = state["messages"][-1]
        assert "ACCOUNTS MARKET" in home["html"] and home["photo"].startswith("media/")
        assert (await client.get(f"/beta/{KEY}/{home['photo']}")).status == 200

        catalog = next(b for row in home["buttons"] for b in row if "Каталог" in b["text"])
        state = await (await client.post(f"/beta/{KEY}/api/action", json={"type": "press", "id": home["id"], "data": catalog["data"]})).json()
        assert "Каталог" in state["messages"][-1]["html"]
        assert len(state["messages"]) == 2, "navigation edits the message instead of adding new ones"

        state = await (await client.post(f"/beta/{KEY}/api/action", json={"type": "text", "text": "<b>hi</b>"})).json()
        assert state["messages"][-2]["mine"] and state["messages"][-2]["html"] == "<b>hi</b>"  # rendered as text by the page

    assert all(v.user_id > USER_ID_BASE for v in site.visitors.values())
    assert site.owns(next(iter(site.visitors.values())).user_id) and not site.owns(123456789)


def test_beta_is_forbidden_in_production(monkeypatch):
    import pytest

    from bot.config import Settings

    monkeypatch.setenv("BETA_SITE", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PAYMENT_PROVIDER", "cryptopay")
    with pytest.raises(ValueError):
        Settings()
