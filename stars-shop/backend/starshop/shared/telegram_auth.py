"""Server-side verification of data signed by Telegram.

* Mini App ``initData`` — https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
  secret = HMAC_SHA256(key="WebAppData", msg=bot_token)
  hash   = hex(HMAC_SHA256(key=secret, msg=data_check_string))
* Login Widget — https://core.telegram.org/widgets/login#checking-authorization
  secret = SHA256(bot_token)

The client-supplied user id, username etc. are only trusted after the hash
matches; everything is parsed from the verified string, never from separate
request fields.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode

from .errors import Unauthorized


@dataclass(frozen=True, slots=True)
class TelegramUser:
    id: int
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool = False
    photo_url: str | None = None
    allows_write_to_pm: bool | None = None


@dataclass(frozen=True, slots=True)
class InitData:
    user: TelegramUser
    auth_date: int
    query_id: str | None = None
    start_param: str | None = None
    chat_type: str | None = None
    raw: dict[str, str] = field(default_factory=dict, repr=False)


def _data_check_string(pairs: dict[str, str]) -> str:
    return "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs) if k != "hash")


def _webapp_secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def validate_init_data(raw: str, bot_token: str, *, max_age_seconds: int, now: float | None = None) -> InitData:
    if not raw or not bot_token:
        raise Unauthorized("Откройте магазин из Telegram", code="init_data_missing")
    try:
        pairs = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise Unauthorized("Некорректные данные Telegram", code="init_data_invalid") from exc

    received_hash = pairs.get("hash", "")
    expected = hmac.new(_webapp_secret(bot_token), _data_check_string(pairs).encode(), hashlib.sha256).hexdigest()
    if not received_hash or not hmac.compare_digest(expected, received_hash):
        raise Unauthorized("Подпись Telegram не прошла проверку", code="init_data_invalid")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise Unauthorized("Некорректные данные Telegram", code="init_data_invalid") from exc
    current = time.time() if now is None else now
    if auth_date <= 0 or current - auth_date > max_age_seconds:
        raise Unauthorized("Сессия устарела. Откройте магазин заново", code="init_data_expired")
    if auth_date - current > 300:
        raise Unauthorized("Некорректное время подписи", code="init_data_invalid")

    try:
        user_obj: dict[str, Any] = json.loads(pairs["user"])
        user = TelegramUser(
            id=int(user_obj["id"]),
            first_name=str(user_obj.get("first_name") or ""),
            last_name=user_obj.get("last_name"),
            username=user_obj.get("username"),
            language_code=user_obj.get("language_code"),
            is_premium=bool(user_obj.get("is_premium", False)),
            photo_url=user_obj.get("photo_url"),
            allows_write_to_pm=user_obj.get("allows_write_to_pm"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise Unauthorized("В данных Telegram нет пользователя", code="init_data_invalid") from exc

    return InitData(
        user=user,
        auth_date=auth_date,
        query_id=pairs.get("query_id"),
        start_param=pairs.get("start_param"),
        chat_type=pairs.get("chat_type"),
        raw=pairs,
    )


def sign_init_data(fields: dict[str, Any], bot_token: str) -> str:
    """Build a correctly signed initData string. Used by tests and by the
    development-only auth helper; production never needs it."""
    pairs = {k: (json.dumps(v, separators=(",", ":"), ensure_ascii=False) if isinstance(v, dict) else str(v)) for k, v in fields.items()}
    pairs["hash"] = hmac.new(_webapp_secret(bot_token), _data_check_string(pairs).encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def validate_login_widget(payload: dict[str, Any], bot_token: str, *, max_age_seconds: int, now: float | None = None) -> TelegramUser:
    data = {k: str(v) for k, v in payload.items() if v is not None}
    received_hash = data.pop("hash", "")
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not received_hash or not hmac.compare_digest(expected, received_hash):
        raise Unauthorized("Подпись Telegram не прошла проверку", code="login_widget_invalid")
    current = time.time() if now is None else now
    auth_date = int(data.get("auth_date", "0") or 0)
    if current - auth_date > max_age_seconds:
        raise Unauthorized("Данные входа устарели", code="login_widget_expired")
    return TelegramUser(
        id=int(data["id"]),
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name"),
        username=data.get("username"),
        photo_url=data.get("photo_url"),
    )
