"""Web panel API: authentication, sessions, CSRF, roles, main flows, exports,
health checks (including an unavailable database)."""

from __future__ import annotations

from decimal import Decimal as D

import httpx
import pytest

from autocommerce.database.enums import RoleCode
from autocommerce.database.session import session_scope
from autocommerce.services import auth
from autocommerce.services.audit import CLI

from .factories import make_product

pytestmark = pytest.mark.usefixtures("seeded")
PASSWORD = "Strong-Pass-2026"


async def make_user(email: str = "owner@shop.test", role: RoleCode = RoleCode.OWNER) -> None:
    async with session_scope() as s:
        await auth.create_user(s, email=email, password=PASSWORD, display_name=email.split("@")[0], role=role, actor=CLI)


async def login(client: httpx.AsyncClient, email: str = "owner@shop.test") -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


async def test_health_endpoints(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["ok"]
    r = await client.get("/api/v1/health/ready")
    assert r.status_code == 200 and r.json()["database"] is True and r.json()["mode"] == "test"


async def test_readiness_reports_unavailable_database(client, monkeypatch):
    from autocommerce.api import app as app_module

    async def down():
        return False, "ConnectionRefusedError"

    monkeypatch.setattr(app_module, "check_database", down)
    r = await client.get("/api/v1/health/ready")
    assert r.status_code == 503 and r.json() == {"ok": False, "database": "ConnectionRefusedError"}


async def test_login_logout_and_session_cookie_flags(client):
    await make_user()
    r = await client.get("/api/v1/dashboard")
    assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": "owner@shop.test", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookie if c.startswith("pac_session="))
    assert "HttpOnly" in session_cookie and "SameSite=strict" in session_cookie
    assert PASSWORD not in r.text and "password_hash" not in r.text
    me = await client.get("/api/v1/auth/me")
    assert me.json()["user"]["role"] == "owner"
    csrf = r.json()["csrf"]
    out = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert out.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_wrong_password_and_lockout(client):
    await make_user()
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"email": "owner@shop.test", "password": "wrong-Password1"})
        assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"email": "owner@shop.test", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "locked"
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@shop.test", "password": PASSWORD})
    assert unknown.status_code == 401 and unknown.json()["error"]["message"] == "Неверный e-mail или пароль"


async def test_csrf_is_required_for_changes(client):
    await make_user()
    csrf = await login(client)
    r = await client.post("/api/v1/security/kill-switch", json={"active": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf"
    r = await client.post("/api/v1/security/kill-switch", json={"active": True, "reason": "test"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["active"] is True


async def test_roles_limit_actions(client):
    await make_user("viewer@shop.test", RoleCode.VIEWER)
    await make_user("operator@shop.test", RoleCode.OPERATOR)
    pid = await make_product()
    csrf = await login(client, "viewer@shop.test")
    assert (await client.get("/api/v1/products")).status_code == 200
    r = await client.post(f"/api/v1/products/{pid}/price", json={"price": "5000"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403
    assert (await client.get("/api/v1/users")).status_code == 403
    client.cookies.clear()
    csrf = await login(client, "operator@shop.test")
    r = await client.post(
        "/api/v1/orders", json={"external_id": "op-1", "items": [{"product_id": pid, "unit_price": "1500"}]}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200 and r.json()["created"]
    r = await client.put("/api/v1/pricing/rules/global", json={"values": {"min_profit_rub": "10"}}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403
    r = await client.post("/api/v1/security/mode", json={"mode": "live"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 403


async def test_price_below_minimum_is_refused(client):
    await make_user()
    csrf = await login(client)
    pid = await make_product(manual_cost="1000")
    detail = (await client.get(f"/api/v1/products/{pid}")).json()
    minimum = D(detail["calculation"]["min_price"])
    r = await client.post(f"/api/v1/products/{pid}/price", json={"price": str(minimum - 1)}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422 and "ниже минимальной" in r.json()["error"]["message"]
    r = await client.post(f"/api/v1/products/{pid}/price", json={"price": str(minimum)}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["product"]["pricing"]["current_price"] == str(minimum)


async def test_listing_flow_with_preview_and_unique_lot(client):
    await make_user()
    csrf = await login(client)
    h = {"X-CSRF-Token": csrf}
    p1 = await make_product(name="Steam Wallet 10 USD")
    p2 = await make_product(name="Steam Wallet 20 USD", manual_cost="1800")
    l1 = (await client.post("/api/v1/listings", json={"product_id": p1}, headers=h)).json()
    dup = await client.post("/api/v1/listings", json={"product_id": p1}, headers=h)
    assert dup.status_code == 409  # one live listing per product
    await client.post(f"/api/v1/listings/{l1['id']}/prepare", headers=h)
    r = await client.post(f"/api/v1/listings/{l1['id']}/publish", headers=h)
    assert r.status_code == 422  # preview first
    await client.post(f"/api/v1/listings/{l1['id']}/confirm-preview", headers=h)
    r = await client.post(f"/api/v1/listings/{l1['id']}/publish", headers=h)
    body = r.json()["result"]
    assert body["mode"] == "manual" and body["steps"] and "PlayerOK" in body["message"]
    r = await client.post(
        f"/api/v1/listings/{l1['id']}/mark-published",
        json={"external_id": "lot-555", "url": "https://playerok.com/products/lot-555"},
        headers=h,
    )
    assert r.json()["listing"]["status"] == "published"
    l2 = (await client.post("/api/v1/listings", json={"product_id": p2}, headers=h)).json()
    await client.post(f"/api/v1/listings/{l2['id']}/prepare", headers=h)
    await client.post(f"/api/v1/listings/{l2['id']}/confirm-preview", headers=h)
    r = await client.post(f"/api/v1/listings/{l2['id']}/mark-published", json={"external_id": "lot-555"}, headers=h)
    assert r.status_code == 409  # the same PlayerOK lot cannot be attached twice


async def test_bulk_publication_requires_confirmation(client):
    await make_user()
    csrf = await login(client)
    h = {"X-CSRF-Token": csrf}
    pid = await make_product()
    lid = (await client.post("/api/v1/listings", json={"product_id": pid}, headers=h)).json()["id"]
    r = await client.post("/api/v1/listings/bulk", json={"ids": [lid], "action": "publish"}, headers=h)
    assert r.json()["needs_confirmation"] and r.json()["first_time"] and r.json()["previews"][0]["title"]
    r = await client.post("/api/v1/listings/bulk", json={"ids": [lid], "action": "publish", "confirm": True}, headers=h)
    assert r.json()["ok"] == [lid]


async def test_dashboard_analytics_and_exports(client):
    await make_user()
    await login(client)
    r = await client.get("/api/v1/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert data["integration"]["capabilities"]["fetch_orders"]["available"] is False
    assert len(data["autosettings"]) == 14
    r = await client.get("/api/v1/analytics", params={"period": "7d"})
    body = r.json()
    assert body["metrics"]["conversion"] is None and body["metrics"]["revenue"] == "0.00"
    assert body["sync"][0]["source"] == "playerok" and body["sync"][0]["status"] == "unavailable"
    xlsx = await client.get("/api/v1/analytics/export", params={"format": "xlsx", "period": "30d"})
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    csv_ = await client.get(
        "/api/v1/analytics/export", params={"format": "csv", "period": "custom", "from": "2026-10-01", "to": "2026-10-25"}
    )
    assert csv_.status_code == 200 and csv_.content.startswith("﻿".encode())
    bad = await client.get("/api/v1/analytics", params={"period": "custom", "from": "2026-10-25", "to": "2026-10-01"})
    assert bad.status_code == 400


async def test_supplier_credentials_are_never_returned(client):
    await make_user()
    csrf = await login(client)
    suppliers = (await client.get("/api/v1/suppliers")).json()["items"]
    vex = next(s for s in suppliers if s["code"] == "vexboost")
    r = await client.put(
        f"/api/v1/suppliers/{vex['id']}/credentials",
        json={"values": {"api_key": "super-secret-key-123456"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    assert "super-secret-key-123456" not in r.text
    detail = await client.get(f"/api/v1/suppliers/{vex['id']}")
    assert "super-secret-key-123456" not in detail.text
    audit = await client.get("/api/v1/audit")
    assert "super-secret-key-123456" not in audit.text
    blocked = next(s for s in suppliers if s["code"] == "kosell")
    r = await client.patch(f"/api/v1/suppliers/{blocked['id']}", json={"purchase_mode": "auto"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422


async def test_code_reveal_is_audited(client):
    await make_user()
    csrf = await login(client)
    h = {"X-CSRF-Token": csrf}
    pid = await make_product()
    await client.post(f"/api/v1/products/{pid}/codes", json={"codes": ["SECRET-CODE-9999"]}, headers=h)
    order = (
        await client.post(
            "/api/v1/orders", json={"external_id": "c-1", "items": [{"product_id": pid, "unit_price": "1500"}], "is_test": False}, headers=h
        )
    ).json()["order"]
    from autocommerce.database.session import session_scope as scope
    from autocommerce.services import orders

    async with scope() as s:
        await orders.process(s, order["id"])
    detail = (await client.get(f"/api/v1/orders/{order['id']}")).json()
    assert "SECRET-CODE-9999" not in str(detail)
    code_id = detail["fulfilment"][0]["codes"][0]["id"]
    r = await client.post(f"/api/v1/codes/{code_id}/reveal", headers=h)
    assert r.json()["code"] == "SECRET-CODE-9999"
    audit = (await client.get("/api/v1/audit", params={"q": "code.reveal"})).json()
    assert audit["total"] == 1 and "SECRET-CODE-9999" not in str(audit)


async def test_validation_errors_are_readable(client):
    await make_user()
    csrf = await login(client)
    r = await client.post("/api/v1/orders", json={"external_id": "", "items": []}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_fx_sync_from_panel(client):
    from .conftest import mock_http

    xml = (
        '<?xml version="1.0" encoding="windows-1251"?><ValCurs Date="24.10.2026" name="Foreign Currency Market">'
        '<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal><Name>Dollar</Name><Value>80,5381</Value></Valute>'
        "</ValCurs>"
    ).encode("cp1251")
    mock_http(lambda request: httpx.Response(200, content=xml))
    await make_user()
    csrf = await login(client)
    r = await client.post("/api/v1/fx/sync", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["run"]["status"] == "succeeded"
    usd = r.json()["items"][0]
    assert usd["currency"] == "USD" and D(usd["rate"]) == D("80.5381")
    await make_user("viewer@shop.test", RoleCode.VIEWER)
    viewer_csrf = await login(client, "viewer@shop.test")
    assert (await client.post("/api/v1/fx/sync", headers={"X-CSRF-Token": viewer_csrf})).status_code == 403


async def test_template_file_is_served_only_from_templates_dir(client):
    from autocommerce.imaging import templates

    templates.ensure_demo_files()
    async with session_scope() as s:
        await templates.sync_registry(s)
    await make_user()
    await login(client)
    r = await client.get("/api/v1/images/templates/demo-graphite/file")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert (await client.get("/api/v1/images/templates/no-such/file")).status_code == 404
    async with session_scope() as s:
        from sqlalchemy import update

        from autocommerce.database.models import ImageTemplate

        await s.execute(update(ImageTemplate).where(ImageTemplate.code == "demo-graphite").values(base_path="../../../etc/passwd"))
    assert (await client.get("/api/v1/images/templates/demo-graphite/file")).status_code == 404


async def test_order_poll_action_keeps_status_outside_processing(client):
    await make_user()
    csrf = await login(client)
    pid = await make_product(manual_cost="100")
    r = await client.post(
        "/api/v1/orders",
        json={"external_id": "poll-1", "items": [{"product_id": pid, "quantity": 1, "unit_price": "500"}]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    oid = r.json()["order"]["id"]
    r = await client.post(f"/api/v1/orders/{oid}/action", json={"action": "poll"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["order"]["status"] != "processing"


def test_production_start_refuses_unsafe_config(monkeypatch):
    from autocommerce import config

    with monkeypatch.context() as m:
        m.setenv("APP_ENV", "production")
        m.setenv("SECRET_KEY", "")
        m.setenv("CREDENTIALS_KEY", "")
        config.reset_settings_cache()
        try:
            with pytest.raises(SystemExit) as stopped:
                config.ensure_startup_config("api")
            assert "SECRET_KEY" in str(stopped.value) and "CREDENTIALS_KEY" in str(stopped.value)
        finally:
            config.reset_settings_cache()
    config.reset_settings_cache()
    config.ensure_startup_config("api")  # the test configuration itself is accepted
