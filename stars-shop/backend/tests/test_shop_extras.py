"""Recipient checks with avatars, the bot button builder, error logs and the
referral overview."""

from __future__ import annotations

import time

import httpx
from sqlalchemy import select

from starshop.database.enums import AdminRole
from starshop.database.models import AdminAuditLog, BotButton, ErrorEvent
from starshop.delivery import registry as delivery_registry
from starshop.delivery.base import RecipientCheck
from starshop.delivery.demo import DemoDeliveryProvider
from starshop.services import recipients
from tests.conftest import admin_client, create_order, get_user, pay_demo, tma


async def check(client, username: str, telegram_id: int = 100001) -> dict:
    r = await client.post("/api/v1/recipients/check", json={"username": username}, headers=tma(telegram_id, "buyer"))
    assert r.status_code == 200, r.text
    return r.json()


async def test_recipient_statuses_are_honest(client, session):
    # Unknown account, DEMO delivery cannot look it up: not claimed to exist.
    r = await check(client, " @Some_Friend ")
    assert r["status"] == "unverified" and r["username"] == "Some_Friend" and r["photo_url"] is None
    assert "Не удалось подтвердить" in r["message"]

    # A user of the shop is known from data signed by Telegram.
    await client.get("/api/v1/me", headers=tma(5555, "boris"))
    r = await check(client, "@BORIS")
    assert r["status"] == "verified" and r["display_name"] == "Test" and r["source"] == "shop"
    assert r["photo_url"].startswith("/api/v1/avatars/5555?e=")

    r = await check(client, "buyer")
    assert r["is_self"] is True

    bad = await client.post("/api/v1/recipients/check", json={"username": "a b"}, headers=tma())
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "recipient_invalid"


async def test_provider_decides_not_found_and_verified(client, session, product):
    class Fragment(DemoDeliveryProvider):
        name = "demo"

        async def check_recipient(self, username: str) -> RecipientCheck:
            if username == "ghost_user":
                return RecipientCheck(ok=False, reason="Пользователь с таким username не найден")
            return RecipientCheck(ok=True, verified=True, display_name="Pavel", photo_url="https://cdn.example/p.jpg")

    delivery_registry.override_provider(Fragment())
    r = await check(client, "ghost_user")
    assert r["ok"] is False and r["status"] == "not_found"
    r = await check(client, "real_user")
    assert r["status"] == "verified" and r["display_name"] == "Pavel" and r["photo_url"] == "https://cdn.example/p.jpg"
    # Orders refuse a recipient the provider does not know.
    body = {"product_id": product.id, "recipient": {"type": "username", "username": "ghost_user"}, "payment_provider": "demo"}
    resp = await client.post("/api/v1/orders", json=body, headers={**tma(), "Idempotency-Key": "k" * 16})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "recipient_not_found"


async def test_avatar_link_must_be_signed(client, session, monkeypatch):
    await client.get("/api/v1/me", headers=tma(5555, "boris"))
    user = await get_user(session, 5555)
    url = recipients.avatar_url(user)
    assert url is not None
    forged = await client.get("/api/v1/avatars/5555?e=9999999999&s=deadbeef")
    assert forged.status_code == 404

    async def fake(telegram_id: int):
        assert telegram_id == 5555
        return b"\xff\xd8jpeg", "image/jpeg"

    from starshop.api.routes import recipients as route

    monkeypatch.setattr(route, "_download_avatar", fake)
    r = await client.get(url)
    assert r.status_code == 200 and r.content == b"\xff\xd8jpeg" and r.headers["content-type"] == "image/jpeg"
    expired = await client.get(f"/api/v1/avatars/5555?e={int(time.time()) - 10}&s=x")
    assert expired.status_code == 404


async def test_bot_button_builder(client, session, product):
    csrf = await admin_client(client, session)
    data = (await client.get("/api/v1/admin/bot-buttons", headers=csrf)).json()
    assert data["items"] == [] and {"id": "buy", "title": "Купить Stars"} in data["options"]["sections"]

    bad = [
        {"title": "Сайт", "action": "url", "url": "javascript:alert(1)"},
        {"title": "Сайт", "action": "url", "url": "http://example.com"},
        {"title": "Стр", "action": "webapp", "url": "https://evil.example/"},
        {"title": "Раздел", "action": "section", "section": "admin"},
        {"title": "Текст", "action": "message", "text": "  "},
        {"title": "Пакет", "action": "product", "product_id": 999},
    ]
    for body in bad:
        r = await client.post("/api/v1/admin/bot-buttons", json=body, headers=csrf)
        assert r.status_code == 422, body

    r = await client.post(
        "/api/v1/admin/bot-buttons",
        json={"title": "Канал", "emoji": "📣", "action": "url", "url": "https://t.me/durov", "style": "primary", "text": "ignored"},
        headers=csrf,
    )
    assert r.status_code == 201
    button = r.json()
    assert button["url"] == "https://t.me/durov" and button["text"] is None and button["style"] == "primary"

    r = await client.put(
        f"/api/v1/admin/bot-buttons/{button['id']}",
        json={"title": "Lucky", "action": "webapp", "url": "/lucky", "row": 1, "is_active": False},
        headers=csrf,
    )
    assert r.json()["url"] == "/lucky" and r.json()["is_active"] is False
    assert (await client.delete(f"/api/v1/admin/bot-buttons/{button['id']}", headers=csrf)).json() == {"ok": True}
    assert await session.scalar(select(BotButton.id)) is None
    actions = (await session.execute(select(AdminAuditLog.action))).scalars().all()
    assert {"bot_button.create", "bot_button.update", "bot_button.delete"} <= set(actions)


async def test_bot_buttons_need_a_manager(client, session):
    csrf = await admin_client(client, session, role=AdminRole.support, telegram_id=900002)
    r = await client.post("/api/v1/admin/bot-buttons", json={"title": "X", "action": "message", "text": "hi"}, headers=csrf)
    assert r.status_code == 403
    client.cookies.clear()
    anonymous = await client.get("/api/v1/admin/bot-buttons")
    assert anonymous.status_code == 401


async def test_client_and_server_errors_are_logged_without_secrets(client, session):
    token = "123456789:AAsecretSECRETsecretSECRETsecret1234"
    r = await client.post(
        "/api/v1/client-errors", json={"kind": "chunk", "message": f"failed with {token}", "path": "/lucky", "stack": "at x"}
    )
    assert r.status_code == 204
    event = (await session.execute(select(ErrorEvent))).scalar_one()
    assert event.source == "client" and token not in event.message and "<bot-token>" in event.message

    csrf = await admin_client(client, session)
    data = (await client.get("/api/v1/admin/errors", headers=csrf)).json()
    assert data["total"] == 1 and data["items"][0]["path"] == "/lucky"
    assert data["problems"] == {"failed_orders": 0, "deliveries_need_attention": 0, "failed_notifications": 0}
    assert (await client.delete("/api/v1/admin/errors", headers=csrf)).json()["removed"] == 1


async def test_referral_overview_and_bonus_ledger(client, session, product):
    inviter = await client.get("/api/v1/me", headers=tma(7001, "inviter"))
    code = inviter.json()["bonus"]["referral_code"]
    await client.get("/api/v1/me", headers=tma(7002, "friend", start_param=f"ref_{code}"))
    data = (await client.get("/api/v1/me/referrals", headers=tma(7001, "inviter"))).json()
    assert data["enabled"] is True and data["link"] == f"https://t.me/pulsar_test_bot?start=ref_{code}"
    assert data["invited"] == 1 and data["activated"] == 0 and data["earned"] == "0.00"
    assert data["referrals"][0]["name"].startswith("@fr") and data["referrals"][0]["status"] == "pending"

    # DEMO orders never bring a reward (only confirmed real payments do).
    order = await create_order(client, product.id, telegram_id=7002, username="friend")
    await pay_demo(client, order["id"], telegram_id=7002, username="friend")
    data = (await client.get("/api/v1/me/referrals", headers=tma(7001, "inviter"))).json()
    assert data["activated"] == 0 and data["history"] == []

    csrf = await admin_client(client, session)
    ledger = (await client.get("/api/v1/admin/bonus-transactions", headers=csrf)).json()
    assert ledger == {"items": [], "total": 0}


def test_check_url_rejects_unsafe_links():
    from starshop.services.bot_buttons import check_url
    from starshop.shared.errors import ValidationFailed

    assert check_url(" https://t.me/x ") == "https://t.me/x"
    for url in ("http://t.me", "tg://resolve", "https://", "https://a b.com", "data:text/html,1"):
        try:
            check_url(url)
        except ValidationFailed:
            continue
        raise AssertionError(url)


async def test_telegram_unreachable_does_not_break_avatar(client, session, monkeypatch):
    await client.get("/api/v1/me", headers=tma(5555, "boris"))
    url = recipients.avatar_url(await get_user(session, 5555))

    from starshop.api.routes import recipients as route

    async def down(telegram_id: int):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(route, "_download_avatar", down)
    assert (await client.get(url)).status_code == 404
