"""Notifications sender, rate limiting, support, health, log masking."""

from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy import select

from starshop.database.enums import NotificationStatus
from starshop.database.models import Notification
from starshop.logging_setup import JsonFormatter, ScrubFilter
from starshop.notifications.sender import TelegramSender, send_due
from starshop.shared.masking import mask_username, scrub
from tests.conftest import BOT_TOKEN, admin_client, create_order, tma


async def test_sender_handles_flood_wait_and_blocked_users(session, client, product):
    await create_order(client, product.id)
    await client.post(f"/api/v1/orders/{(await create_order(client, product.id))['id']}/payment", json={"provider": "demo"}, headers=tma())
    session.add(Notification(chat_id=1, kind="x", text="hi", dedup_key="blocked"))
    session.add(Notification(chat_id=2, kind="x", text="hi", dedup_key="flood"))
    await session.commit()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert request.url.path == f"/bot{BOT_TOKEN}/sendMessage"
        if body["chat_id"] == 1:
            return httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})
        if body["chat_id"] == 2:
            return httpx.Response(429, json={"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 7}})
        return httpx.Response(200, json={"ok": True, "result": {}})

    sender = TelegramSender(transport=httpx.MockTransport(handler))
    await send_due(session, sender)
    await session.commit()
    rows = {n.dedup_key: n for n in (await session.execute(select(Notification))).scalars()}
    assert rows["blocked"].status == NotificationStatus.failed
    assert rows["flood"].status == NotificationStatus.pending and rows["flood"].attempts == 1
    sent = [n for n in rows.values() if n.status == NotificationStatus.sent]
    assert sent and all("web_app" in json.dumps(n.reply_markup) for n in sent if n.reply_markup)
    await sender.close()


async def test_rate_limit(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_per_ip_per_minute", 5)
    codes = [(await client.get("/api/v1/catalog")).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[-1] == 429
    assert (await client.get("/api/health")).status_code == 200  # exempt


async def test_support_ticket_flow(client, session, product):
    order = await create_order(client, product.id)
    csrf = await admin_client(client, session)
    r = await client.post("/api/v1/support/tickets", json={"text": "Где мои звёзды?", "order_id": order["id"]}, headers=tma())
    assert r.status_code == 201, r.text
    ticket_id = r.json()["id"]
    assert (await client.get(f"/api/v1/support/tickets/{ticket_id}", headers=tma(2, "other"))).status_code == 404
    r = await client.post(f"/api/v1/admin/tickets/{ticket_id}/reply", json={"text": "Уже проверяем!"}, headers=csrf)
    assert r.json()["status"] == "answered"
    t = (await client.get(f"/api/v1/support/tickets/{ticket_id}", headers=tma())).json()
    assert [m["author"] for m in t["messages"]] == ["user", "admin"]
    assert "admin_id" not in t["messages"][1]
    kinds = set((await session.execute(select(Notification.kind))).scalars())
    assert {"support_reply", "admin_new_ticket"} <= kinds


async def test_health(client):
    assert (await client.get("/api/health")).json() == {"status": "ok"}
    ready = (await client.get("/api/health/ready")).json()
    assert ready["database"] is True


def test_secrets_are_scrubbed_from_logs():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, f"calling https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", None, None)
    record.payload = {"api_token": "abc", "nested": {"init_data": "query_id=..."}, "ok": 1}
    ScrubFilter().filter(record)
    line = JsonFormatter("test").format(record)
    assert BOT_TOKEN not in line and "abc" not in line and "query_id" not in line
    assert scrub({"Authorization": "tma x"})["Authorization"] == "***"
    assert mask_username("durov") == "@du**v"
