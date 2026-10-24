"""Who receives the Stars when a customer buys for someone else.

The Bot API cannot look a user up by @username, so the answer is built from
what can actually be confirmed:

* the username belongs to a user of this shop (seen through data signed by
  Telegram) — name, Telegram ID and avatar are known;
* the delivery provider confirms the account (e.g. a Fragment-based
  supplier) — its name and photo are shown;
* otherwise the status is ``unverified``: the format is valid, but nobody
  confirmed the account exists. The customer sees that before paying.

A provider answer "not found" stops the order.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.models import User
from ..delivery.base import DeliveryProvider
from ..shared.demo_identity import ID_BASE

AVATAR_TTL = 3600


@dataclass(slots=True)
class Recipient:
    username: str
    # unavailable: the account may exist, but this delivery channel cannot reach it.
    status: Literal["verified", "unverified", "not_found", "unavailable"]
    name: str | None = None
    photo_url: str | None = None
    telegram_id: int | None = None
    is_self: bool = False
    source: Literal["shop", "provider"] | None = None
    message: str | None = None


def _avatar_signature(telegram_id: int, expires: int) -> str:
    key = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(key, f"avatar:{telegram_id}:{expires}".encode(), hashlib.sha256).hexdigest()[:32]


def avatar_url(user: User) -> str | None:
    """A Telegram CDN picture from the Mini App, or a short-lived signed link
    to the avatar endpoint (the bot reads the profile photo)."""
    if user.photo_url:
        return user.photo_url
    if user.telegram_id >= ID_BASE or not get_settings().bot_token.get_secret_value():
        return None
    expires = (int(time.time()) // AVATAR_TTL + 2) * AVATAR_TTL  # stable within the hour: cacheable
    return f"/api/v1/avatars/{user.telegram_id}?e={expires}&s={_avatar_signature(user.telegram_id, expires)}"


def avatar_link_valid(telegram_id: int, expires: int, signature: str) -> bool:
    return expires >= time.time() and hmac.compare_digest(_avatar_signature(telegram_id, expires), signature)


async def find_shop_user(session: AsyncSession, username: str) -> User | None:
    return (
        await session.execute(
            select(User)
            .where(func.lower(User.username) == username.lower(), User.telegram_id < ID_BASE, User.is_blocked.is_(False))
            .order_by(User.last_seen_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def lookup(session: AsyncSession, buyer: User, username: str, delivery: DeliveryProvider) -> Recipient:
    """``username`` must already be normalized (``orders.normalize_username``)."""
    if buyer.username and username.lower() == buyer.username.lower():
        return Recipient(
            username=buyer.username,
            status="verified",
            name=buyer.display_name,
            photo_url=avatar_url(buyer),
            telegram_id=buyer.telegram_id,
            is_self=True,
            source="shop",
        )
    check = await delivery.check_recipient(username)
    if not check.ok:
        return Recipient(username=username, status="not_found", message=check.reason or "Пользователь с таким username не найден")
    known = await find_shop_user(session, username)
    if known is not None:
        return Recipient(
            username=known.username or username,
            status="verified",
            name=known.display_name,
            photo_url=avatar_url(known),
            telegram_id=known.telegram_id,
            source="shop",
        )
    if delivery.requires_telegram_id:
        return Recipient(
            username=username,
            status="unavailable",
            message="Подарить Premium можно только тому, кто уже открывал этот магазин или бота: попросите получателя запустить бота",
        )
    if check.verified:
        return Recipient(username=username, status="verified", name=check.display_name, photo_url=check.photo_url, source="provider")
    return Recipient(
        username=username,
        status="unverified",
        message="Не удалось подтвердить, что такой аккаунт существует. Проверьте username перед оплатой",
    )
