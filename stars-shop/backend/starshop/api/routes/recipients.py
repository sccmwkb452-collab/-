"""Gift recipients: checking a @username and showing the avatar."""

from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query, Response

from ...config import get_settings
from ...services import orders as order_service
from ...services import recipients
from ...shared.errors import NotFound, ValidationFailed
from ..deps import RuntimeDep, SessionDep, UserDep, ip_rate_limit, user_rate_limit
from ..schemas import RecipientCheckIn

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/recipients/check", dependencies=[Depends(user_rate_limit("recipient", 20))])
async def check_recipient(body: RecipientCheckIn, user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    delivery = order_service.active_delivery_provider(runtime)
    if not (runtime.shop.allow_gift_to_others and delivery.supports_gift_to_others):
        raise ValidationFailed("Покупка для другого пользователя сейчас недоступна", code="gifts_disabled")
    username = order_service.normalize_username(body.username)
    found = await recipients.lookup(session, user, username, delivery)
    return {
        "ok": found.status != "not_found",
        "status": found.status,
        "username": found.username,
        "display_name": found.name,
        "photo_url": found.photo_url,
        "is_self": found.is_self,
        "source": found.source,
        "message": found.message,
    }


async def _download_avatar(telegram_id: int) -> tuple[bytes, str] | None:
    s = get_settings()
    token = s.bot_token.get_secret_value()
    base = s.telegram_api_base.rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{base}/bot{token}/getUserProfilePhotos", json={"user_id": telegram_id, "limit": 1})
        photos = (r.json().get("result") or {}).get("photos") or []
        if not photos:
            return None
        sizes = sorted(photos[0], key=lambda p: p.get("width", 0))
        size = next((p for p in sizes if p.get("width", 0) >= 160), sizes[-1])
        r = await client.post(f"{base}/bot{token}/getFile", json={"file_id": size["file_id"]})
        path = (r.json().get("result") or {}).get("file_path")
        if not path:
            return None
        r = await client.get(f"{base}/file/bot{token}/{path}")
        if r.status_code != 200 or len(r.content) > 2_000_000:
            return None
        return r.content, r.headers.get("content-type", "image/jpeg")


@router.get("/avatars/{telegram_id}", dependencies=[Depends(ip_rate_limit("avatar", 120))])
async def avatar(telegram_id: int, e: Annotated[int, Query()], s: Annotated[str, Query(max_length=64)]) -> Response:
    """Profile photo through the bot (the file URL contains the bot token, so
    it never reaches the browser). Only links signed by the server work."""
    if not recipients.avatar_link_valid(telegram_id, e, s):
        raise NotFound("Аватар недоступен", code="avatar_unavailable")
    try:
        result = await _download_avatar(telegram_id)
    except (httpx.HTTPError, ValueError, KeyError):
        log.warning("avatar download failed", extra={"telegram_id": telegram_id})
        result = None
    if result is None:
        raise NotFound("Аватар недоступен", code="avatar_unavailable")
    content, media_type = result
    return Response(
        content,
        media_type=media_type if media_type.startswith("image/") else "image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
