"""Notifications: transactional outbox + Telegram delivery.

``notify`` writes rows in the caller's transaction, so a notification exists
exactly when the event that caused it was committed. The worker sends them
through the Bot API directly (the worker does not need the bot process),
respecting 429 ``retry_after``, quiet hours and per-kind switches.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import NotificationStatus, Severity
from ..database.models import Notification
from ..shared.masking import scrub_text
from ..shared.timeutil import local_tz, utcnow
from . import app_settings
from .auth import owner_chat_ids

log = logging.getLogger(__name__)

SEVERITY_ICON = {Severity.INFO: "ℹ️", Severity.SUCCESS: "✅", Severity.WARNING: "⚠️", Severity.CRITICAL: "🚨"}
MAX_ATTEMPTS = 6

Button = dict[str, Any]


def btn(text: str, callback: str | None = None, *, url: str | None = None, copy: str | None = None) -> Button:
    if url:
        return {"text": text, "url": url}
    if copy is not None:
        return {"text": text, "copy_text": {"text": copy[:256]}}
    return {"text": text, "callback_data": callback or "noop"}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def _in_quiet_hours(now_local: datetime, start: str, end: str) -> bool:
    s = time.fromisoformat(start)
    e = time.fromisoformat(end)
    t = now_local.time()
    return s <= t < e if s < e else (t >= s or t < e)


def _quiet_until(now_local: datetime, end: str) -> datetime:
    e = time.fromisoformat(end)
    target = now_local.replace(hour=e.hour, minute=e.minute, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return target


async def notify(
    session: AsyncSession,
    kind: str,
    title: str,
    body: str,
    *,
    severity: Severity = Severity.INFO,
    buttons: list[list[Button]] | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    dedupe_key: str | None = None,
    permission: str | None = "view",
    chat_ids: list[int] | None = None,
) -> int:
    """Queue a notification for every recipient. Returns the number queued."""
    prefs = await app_settings.get_setting(session, "notifications")
    enabled = prefs["kinds"].get(kind, True) or severity is Severity.CRITICAL
    recipients = chat_ids if chat_ids is not None else await owner_chat_ids(session, permission)
    next_at = utcnow()
    qh = prefs["quiet_hours"]
    if qh.get("enabled") and severity is not Severity.CRITICAL:
        now_local = utcnow().astimezone(local_tz())
        if _in_quiet_hours(now_local, qh["start"], qh["end"]):
            next_at = _quiet_until(now_local, qh["end"])
    if not recipients:
        recipients = [0]  # still recorded (visible in the panel), marked suppressed
    count = 0
    for chat_id in recipients:
        status = NotificationStatus.PENDING if enabled and chat_id else NotificationStatus.SUPPRESSED
        stmt = (
            insert(Notification)
            .values(
                kind=kind,
                severity=severity,
                title=title[:200],
                body=scrub_text(body)[:3500],
                buttons=buttons or [],
                entity_type=entity_type,
                entity_id=entity_id,
                chat_id=chat_id or None,
                status=status,
                dedupe_key=f"{dedupe_key}:{chat_id}" if dedupe_key else None,
                next_attempt_at=next_at,
            )
            .on_conflict_do_nothing(index_elements=[Notification.dedupe_key])
        )
        result = await session.execute(stmt)
        count += result.rowcount or 0
    return count


def render(n: Notification) -> str:
    icon = SEVERITY_ICON.get(n.severity, "•")
    return f"{icon} <b>{esc(n.title)}</b>\n\n{n.body}"


@dataclass
class SendResult:
    ok: bool
    retry_after: float | None = None
    permanent: bool = False
    error: str = ""


class TelegramSender:
    """Minimal Bot API client for the worker (no aiogram dependency)."""

    def __init__(self, token: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        settings = get_settings()
        self.token = token if token is not None else settings.bot_token.get_secret_value()
        self.base = settings.telegram_api_base
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def call(self, method: str, payload: dict[str, Any]) -> SendResult:
        url = f"{self.base}/bot{self.token}/{method}"
        try:
            async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
                response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            return SendResult(False, error=type(exc).__name__)
        try:
            data = response.json()
        except ValueError:
            return SendResult(False, error=f"HTTP {response.status_code}")
        if data.get("ok"):
            return SendResult(True)
        params = data.get("parameters") or {}
        if response.status_code == 429 or "retry_after" in params:
            return SendResult(False, retry_after=float(params.get("retry_after", 5)), error="rate limited")
        permanent = response.status_code in (400, 403)
        return SendResult(False, permanent=permanent, error=scrub_text(str(data.get("description", "")))[:300])

    async def send_message(self, chat_id: int, text: str, buttons: list[list[Button]] | None = None) -> SendResult:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML", "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        return await self.call("sendMessage", payload)


_sender_override: TelegramSender | None = None


def get_sender() -> TelegramSender:
    return _sender_override or TelegramSender()


def set_sender(sender: TelegramSender | None) -> None:
    global _sender_override
    _sender_override = sender


async def send_pending(session: AsyncSession, *, limit: int = 20) -> dict[str, int]:
    """Send due notifications. Runs inside the worker's unit of work."""
    sender = get_sender()
    stats = {"sent": 0, "failed": 0, "retry": 0}
    if not sender.configured:
        return stats
    rows = (
        await session.execute(
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING, Notification.next_attempt_at <= utcnow())
            .order_by(Notification.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).scalars()
    for n in rows:
        assert n.chat_id is not None
        result = await sender.send_message(n.chat_id, render(n), n.buttons or None)
        n.attempts += 1
        if result.ok:
            n.status = NotificationStatus.SENT
            n.sent_at = utcnow()
            n.last_error = None
            stats["sent"] += 1
        elif result.permanent or n.attempts >= MAX_ATTEMPTS:
            n.status = NotificationStatus.FAILED
            n.last_error = result.error
            stats["failed"] += 1
        else:
            delay = result.retry_after or min(600, 5 * 2**n.attempts)
            n.next_attempt_at = utcnow() + timedelta(seconds=delay)
            n.last_error = result.error
            stats["retry"] += 1
            if result.retry_after:
                break  # global flood limit: stop this batch
    return stats
