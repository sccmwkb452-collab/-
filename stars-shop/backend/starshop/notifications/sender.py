"""Delivers queued notifications through the Bot API."""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import NotificationStatus
from ..database.models import Notification
from ..shared.timeutil import utcnow

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 8


class TelegramSender:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        s = get_settings()
        self._token = s.bot_token.get_secret_value()
        self._client = httpx.AsyncClient(base_url=s.telegram_api_base, timeout=15, transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    async def send(self, n: Notification) -> tuple[bool, str | None, int | None]:
        """Returns ``(ok, error, retry_after)``; ``retry_after`` of -1 means
        the error is permanent."""
        if not self._token:
            return False, "BOT_TOKEN is not configured", 300
        payload = {"chat_id": n.chat_id, "text": n.text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
        if n.reply_markup:
            payload["reply_markup"] = n.reply_markup
        try:
            r = await self._client.post(f"/bot{self._token}/sendMessage", json=payload)
        except httpx.HTTPError as exc:
            return False, f"network: {exc.__class__.__name__}", None
        if r.status_code == 200:
            return True, None, None
        try:
            data = r.json()
        except ValueError:
            data = {}
        desc = str(data.get("description", r.status_code))
        if r.status_code == 429:
            return False, desc, int((data.get("parameters") or {}).get("retry_after", 5))
        if r.status_code in (400, 403):
            # Chat not found / bot blocked by the user: retrying will not help.
            return False, desc, -1
        return False, desc, None


async def send_due(session: AsyncSession, sender: TelegramSender, limit: int = 25) -> int:
    rows = (
        (
            await session.execute(
                select(Notification)
                .where(Notification.status == NotificationStatus.pending, Notification.next_attempt_at <= utcnow())
                .order_by(Notification.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for n in rows:
        ok, error, retry_after = await sender.send(n)
        n.attempts += 1
        if ok:
            n.status = NotificationStatus.sent
            n.sent_at = utcnow()
            n.last_error = None
            continue
        n.last_error = (error or "")[:500]
        if retry_after == -1 or n.attempts >= MAX_ATTEMPTS:
            n.status = NotificationStatus.failed
        else:
            delay = retry_after if retry_after is not None else min(2**n.attempts * 5, 1800)
            n.next_attempt_at = utcnow() + timedelta(seconds=delay)
        if retry_after and retry_after > 0:
            break  # global flood limit: stop this batch
    return len(rows)
