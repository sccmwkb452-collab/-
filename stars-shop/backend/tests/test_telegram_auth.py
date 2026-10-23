from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl, urlencode

import pytest

from starshop.shared.errors import Unauthorized
from starshop.shared.telegram_auth import validate_init_data, validate_login_widget
from tests.conftest import BOT_TOKEN, init_data, tma


def test_valid_init_data_is_accepted():
    data = validate_init_data(init_data(42, "alice", start_param="ref_ABCDEF"), BOT_TOKEN, max_age_seconds=3600)
    assert data.user.id == 42
    assert data.user.username == "alice"
    assert data.start_param == "ref_ABCDEF"


def test_tampered_user_is_rejected():
    raw = init_data(42, "alice")
    pairs = dict(parse_qsl(raw))
    pairs["user"] = pairs["user"].replace("42", "43")
    with pytest.raises(Unauthorized) as exc:
        validate_init_data(urlencode(pairs), BOT_TOKEN, max_age_seconds=3600)
    assert exc.value.code == "init_data_invalid"


def test_signature_from_another_bot_is_rejected():
    raw = init_data(42, "alice", token="987654321:AAanotherBOTtokenANOTHERbotTOKEN0000")
    with pytest.raises(Unauthorized):
        validate_init_data(raw, BOT_TOKEN, max_age_seconds=3600)


def test_expired_init_data_is_rejected():
    raw = init_data(42, "alice", auth_date=int(time.time()) - 7200)
    with pytest.raises(Unauthorized) as exc:
        validate_init_data(raw, BOT_TOKEN, max_age_seconds=3600)
    assert exc.value.code == "init_data_expired"


def test_missing_hash_and_garbage_are_rejected():
    with pytest.raises(Unauthorized):
        validate_init_data("user=%7B%22id%22%3A1%7D&auth_date=1", BOT_TOKEN, max_age_seconds=3600)
    with pytest.raises(Unauthorized):
        validate_init_data("", BOT_TOKEN, max_age_seconds=3600)


def test_login_widget_hash():
    now = int(time.time())
    payload = {"id": 900001, "first_name": "Owner", "username": "owner", "auth_date": now}
    check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    payload["hash"] = hmac.new(hashlib.sha256(BOT_TOKEN.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    assert validate_login_widget(payload, BOT_TOKEN, max_age_seconds=600).id == 900001
    payload["id"] = 900002
    with pytest.raises(Unauthorized):
        validate_login_widget(payload, BOT_TOKEN, max_age_seconds=600)


async def test_api_requires_valid_signature(client):
    assert (await client.get("/api/v1/me")).status_code == 401
    bad = {"Authorization": "tma " + init_data(1, "x").replace("hash=", "hash=00")}
    r = await client.get("/api/v1/me", headers=bad)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "init_data_invalid"
    ok = await client.get("/api/v1/me", headers=tma(555, "carol"))
    assert ok.status_code == 200
    assert ok.json()["user"]["telegram_id"] == 555


async def test_client_supplied_identity_fields_are_ignored(client, product):
    """Body fields cannot override who the buyer is."""
    r = await client.post(
        "/api/v1/orders",
        json={"product_id": product.id, "recipient": {"type": "self"}, "payment_provider": "demo", "user_id": 1},
        headers={**tma(777, "dave"), "Idempotency-Key": "k" * 16},
    )
    assert r.status_code == 422  # unknown fields are rejected outright
