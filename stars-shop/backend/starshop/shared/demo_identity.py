"""Anonymous visitors of a public DEMO site (``PUBLIC_DEMO=true``).

Outside Telegram the Mini App keeps a random key in the browser and sends
``Authorization: demo <key>``. The server maps the key to a stable user id
with HMAC(secret_key), so nobody can choose an id or act as another visitor
without their key. The ids start at 2**52, above every Telegram user id
(Telegram ids have at most 52 significant bits): a visitor never becomes a
real Telegram user, and the admin panel accepts only data signed by Telegram.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time

from .errors import Unauthorized
from .telegram_auth import InitData, TelegramUser

ID_BASE = 2**52
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")


def is_demo_user_id(telegram_id: int) -> bool:
    return telegram_id >= ID_BASE


def demo_init_data(key: str, secret: str) -> InitData:
    if not KEY_RE.fullmatch(key):
        raise Unauthorized("Не удалось войти в демо. Обновите страницу", code="demo_key_invalid")
    digest = hmac.new(secret.encode(), f"demo-visitor:{key}".encode(), hashlib.sha256).digest()
    user = TelegramUser(
        id=ID_BASE + int.from_bytes(digest[:8], "big") % ID_BASE,
        first_name="Гость",
        username=f"demo_{digest[8:12].hex()}",
        language_code="ru",
        allows_write_to_pm=False,
    )
    return InitData(user=user, auth_date=int(time.time()), query_id="demo")
