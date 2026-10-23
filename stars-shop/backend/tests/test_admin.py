from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from starshop.database.enums import AdminRole, OrderStatus
from starshop.database.models import AdminAuditLog, AdminLoginToken, Order
from starshop.services import admin_auth
from starshop.shared.timeutil import utcnow
from tests.conftest import admin_client, create_order, make_admin, pay_demo, tma


async def test_admin_api_requires_session(client):
    for path in ("/api/v1/admin/orders", "/api/v1/admin/dashboard", "/api/v1/admin/settings", "/api/v1/admin/users"):
        r = await client.get(path)
        assert r.status_code == 401, path


async def test_customer_initdata_does_not_grant_admin(client):
    r = await client.get("/api/v1/admin/orders", headers=tma(900001, "owner"))
    assert r.status_code == 401


async def test_login_link_is_single_use_and_expires(client, session):
    admin = await make_admin(session)
    token = await admin_auth.issue_login_token(session, admin)
    await session.commit()
    assert (await client.post("/api/v1/admin/auth/exchange", json={"token": token})).status_code == 200
    again = await client.post("/api/v1/admin/auth/exchange", json={"token": token})
    assert again.status_code == 401
    old = await admin_auth.issue_login_token(session, admin)
    await session.flush()
    row = (await session.execute(select(AdminLoginToken).order_by(AdminLoginToken.id.desc()))).scalars().first()
    row.expires_at = utcnow() - timedelta(seconds=1)
    await session.commit()
    assert (await client.post("/api/v1/admin/auth/exchange", json={"token": old})).status_code == 401


async def test_session_cookie_flags(client, session):
    admin = await make_admin(session)
    token = await admin_auth.issue_login_token(session, admin)
    await session.commit()
    r = await client.post("/api/v1/admin/auth/exchange", json={"token": token})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" in cookie and "path=/api/v1/admin" in cookie
    assert token not in r.text


async def test_csrf_is_required_for_mutations(client, session, product):
    csrf = await admin_client(client, session)
    r = await client.patch(f"/api/v1/admin/products/{product.id}", json={"price": "170.00"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = await client.patch(f"/api/v1/admin/products/{product.id}", json={"price": "170.00"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403
    r = await client.patch(f"/api/v1/admin/products/{product.id}", json={"price": "170.00"}, headers=csrf)
    assert r.status_code == 200 and r.json()["price"] == "170.00"


async def test_role_permissions(client, session, product):
    csrf = await admin_client(client, session, AdminRole.support, telegram_id=900020)
    assert (await client.get("/api/v1/admin/orders", headers=csrf)).status_code == 200
    assert (await client.patch(f"/api/v1/admin/products/{product.id}", json={"price": "1.00"}, headers=csrf)).status_code == 403
    assert (await client.get("/api/v1/admin/dashboard", headers=csrf)).status_code == 403
    assert (await client.put("/api/v1/admin/settings/shop", json={"maintenance": True}, headers=csrf)).status_code == 403
    assert (await client.get("/api/v1/admin/admins", headers=csrf)).status_code == 403


async def test_manager_cannot_change_owner_settings(client, session):
    csrf = await admin_client(client, session, AdminRole.manager, telegram_id=900030)
    r = await client.put("/api/v1/admin/settings/content", json={"catalog_title": "Каталог"}, headers=csrf)
    assert r.status_code == 200
    assert (await client.put("/api/v1/admin/settings/shop", json={"maintenance": True}, headers=csrf)).status_code == 403
    assert (await client.put("/api/v1/admin/settings/referral", json={"enabled": True}, headers=csrf)).status_code == 403


async def test_catalog_changes_are_live_and_audited(client, session, product):
    csrf = await admin_client(client, session)
    r = await client.post(
        "/api/v1/admin/products",
        json={"kind": "package", "stars_amount": 250, "price": "409.00", "is_popular": True, "sort_order": 5},
        headers=csrf,
    )
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    catalog = (await client.get("/api/v1/catalog")).json()["items"]
    assert [p["id"] for p in catalog] == [new_id, product.id]
    assert catalog[0]["is_popular"] is True
    # only one popular product at a time
    await client.patch(f"/api/v1/admin/products/{product.id}", json={"is_popular": True}, headers=csrf)
    catalog = (await client.get("/api/v1/catalog")).json()["items"]
    assert [p["is_popular"] for p in catalog] == [False, True]
    await client.patch(f"/api/v1/admin/products/{new_id}", json={"is_active": False}, headers=csrf)
    assert len((await client.get("/api/v1/catalog")).json()["items"]) == 1
    assert (await client.delete(f"/api/v1/admin/products/{product.id}", headers=csrf)).status_code == 200
    assert (await client.get("/api/v1/catalog")).json()["items"] == []
    actions = list((await session.execute(select(AdminAuditLog.action).order_by(AdminAuditLog.id))).scalars())
    assert actions.count("product.update") == 2 and "product.create" in actions and "product.archive" in actions


async def test_admin_cannot_mark_unpaid_order_paid(client, session, product):
    """There is no 'mark as paid' action; checking with the provider is the
    only path and it requires the provider to confirm."""
    csrf = await admin_client(client, session)
    order = await create_order(client, product.id)
    await client.post(f"/api/v1/orders/{order['id']}/payment", json={"provider": "demo"}, headers=tma())
    detail = (await client.get(f"/api/v1/admin/orders/{order['id']}", headers=csrf)).json()
    assert "mark_paid" not in detail["actions"]
    r = await client.post(f"/api/v1/admin/orders/{order['id']}/check-payment", headers=csrf)
    assert r.json()["order"]["status"] == "pending_payment"
    for path in ("mark-paid", "status"):
        assert (await client.post(f"/api/v1/admin/orders/{order['id']}/{path}", json={"status": "paid"}, headers=csrf)).status_code in (
            404,
            405,
        )
    assert (await client.patch(f"/api/v1/admin/orders/{order['id']}", json={"status": "paid"}, headers=csrf)).status_code == 405


async def test_order_search_and_csv_export(client, session, product):
    csrf = await admin_client(client, session)
    order = await create_order(client, product.id, telegram_id=314159, username="=cmd")
    await pay_demo(client, order["id"], telegram_id=314159, username="=cmd")
    by_number = (await client.get(f"/api/v1/admin/orders?q={order['number']}", headers=csrf)).json()
    by_tg = (await client.get("/api/v1/admin/orders?q=314159", headers=csrf)).json()
    assert by_number["total"] == 1 and by_tg["total"] == 1
    assert (await client.get("/api/v1/admin/orders?status=paid", headers=csrf)).json()["total"] == 1
    r = await client.get("/api/v1/admin/orders/export.csv", headers=csrf)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert len(lines) == 2 and order["number"] in lines[1]
    assert ";'=cmd;" in lines[1]  # formula injection neutralised


async def test_production_switch_requires_real_integrations(client, session):
    csrf = await admin_client(client, session)
    r = await client.put("/api/v1/admin/settings/shop", json={"mode": "production"}, headers=csrf)
    assert r.status_code == 422 and r.json()["error"]["code"] == "production_not_allowed"


async def test_settings_never_expose_secrets(client, session, settings):
    csrf = await admin_client(client, session)
    body = (await client.get("/api/v1/admin/settings", headers=csrf)).text
    assert settings.bot_token.get_secret_value() not in body
    assert settings.cryptopay_api_token.get_secret_value() not in body
    assert settings.secret_key.get_secret_value() not in body


async def test_user_block_and_notes(client, session, product):
    csrf = await admin_client(client, session)
    await client.get("/api/v1/me", headers=tma(4242, "eve"))
    users = (await client.get("/api/v1/admin/users?q=4242", headers=csrf)).json()["items"]
    uid = users[0]["id"]
    assert (await client.post(f"/api/v1/admin/users/{uid}/block", json={"reason": "chargeback abuse"}, headers=csrf)).json()[
        "is_blocked"
    ] is True
    await client.post(f"/api/v1/admin/users/{uid}/notes", json={"text": "Проверить платежи"}, headers=csrf)
    detail = (await client.get(f"/api/v1/admin/users/{uid}", headers=csrf)).json()
    assert detail["notes"][0]["text"] == "Проверить платежи"
    assert {a["action"] for a in detail["audit"]} == {"user.block", "user.note"}
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo"},
        headers={**tma(4242, "eve"), "Idempotency-Key": "abcdefgh1234"},
    )
    assert r.status_code == 403


async def test_dashboard_separates_turnover_and_profit(client, session, product):
    csrf = await admin_client(client, session)
    order = await create_order(client, product.id)
    await pay_demo(client, order["id"])
    from starshop.worker.main import delivery_tick

    await delivery_tick()
    demo_only = (await client.get("/api/v1/admin/dashboard?period=day", headers=csrf)).json()
    assert demo_only["money"]["turnover"] == "0.00"  # DEMO orders excluded by default
    data = (await client.get("/api/v1/admin/dashboard?period=day&include_demo=true", headers=csrf)).json()
    assert data["money"]["turnover"] == "169.00"
    assert data["money"]["profit"] == "49.00"  # 169 - 100 * 1.20
    assert data["orders"]["completed"] == 1
    series = (await client.get("/api/v1/admin/dashboard/series?granularity=day&points=7&include_demo=true", headers=csrf)).json()["items"]
    assert len(series) == 7 and series[-1]["turnover"] == "169.00"
    await session.commit()
    assert (await session.execute(select(Order))).scalar_one().status == OrderStatus.completed
