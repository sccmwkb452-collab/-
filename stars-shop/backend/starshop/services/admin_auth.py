"""Admin authentication without passwords.

* ``/admin`` in the bot issues a one-time login link (5 min, single use,
  only its SHA-256 is stored) for admins listed in ``admin_users``;
* alternatively the panel can be opened inside Telegram (verified initData)
  or via the Telegram Login Widget (verified hash).

A session is an opaque random token in an ``HttpOnly; SameSite=Strict``
cookie; the DB stores only its hash. Mutating requests must also send
``X-CSRF-Token`` = HMAC(secret_key, session token).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import AdminRole
from ..database.models import AdminLoginToken, AdminSession, AdminUser
from ..shared.errors import Forbidden, Unauthorized
from ..shared.ids import sha256_hex, token_urlsafe
from ..shared.timeutil import utcnow


@dataclass(slots=True)
class IssuedSession:
    token: str
    csrf: str
    session: AdminSession


def csrf_for(token: str) -> str:
    key = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(key, b"csrf:" + token.encode(), hashlib.sha256).hexdigest()


async def ensure_bootstrap_admins(session: AsyncSession) -> None:
    """Admins listed in ADMIN_TELEGRAM_IDS always exist as active owners."""
    for telegram_id in get_settings().admin_telegram_ids:
        admin = (await session.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id))).scalar_one_or_none()
        if admin is None:
            session.add(AdminUser(telegram_id=telegram_id, role=AdminRole.owner, is_active=True, display_name="Owner"))
        elif not admin.is_active or admin.role != AdminRole.owner:
            admin.is_active = True
            admin.role = AdminRole.owner


async def admin_by_telegram_id(session: AsyncSession, telegram_id: int) -> AdminUser | None:
    return (
        await session.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id, AdminUser.is_active.is_(True)))
    ).scalar_one_or_none()


async def issue_login_token(session: AsyncSession, admin: AdminUser) -> str:
    token = token_urlsafe(32)
    session.add(
        AdminLoginToken(
            admin_id=admin.id,
            token_hash=sha256_hex(token),
            expires_at=utcnow() + timedelta(minutes=get_settings().admin_login_token_minutes),
        )
    )
    return token


async def consume_login_token(session: AsyncSession, token: str) -> AdminUser:
    row = (
        await session.execute(select(AdminLoginToken).where(AdminLoginToken.token_hash == sha256_hex(token)).with_for_update())
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise Unauthorized("Ссылка для входа недействительна или устарела. Запросите новую командой /admin", code="login_link_invalid")
    row.used_at = utcnow()
    admin = await session.get(AdminUser, row.admin_id)
    if admin is None or not admin.is_active:
        raise Forbidden("Доступ отключён", code="admin_inactive")
    return admin


async def start_session(session: AsyncSession, admin: AdminUser, *, ip: str | None, user_agent: str | None) -> IssuedSession:
    token = token_urlsafe(32)
    row = AdminSession(
        admin_id=admin.id,
        token_hash=sha256_hex(token),
        ip=ip,
        user_agent=(user_agent or "")[:255],
        expires_at=utcnow() + timedelta(hours=get_settings().admin_session_hours),
    )
    session.add(row)
    admin.last_login_at = utcnow()
    return IssuedSession(token=token, csrf=csrf_for(token), session=row)


async def resolve_session(session: AsyncSession, token: str | None) -> tuple[AdminUser, AdminSession]:
    if not token:
        raise Unauthorized(code="admin_session_missing")
    row = (await session.execute(select(AdminSession).where(AdminSession.token_hash == sha256_hex(token)))).scalar_one_or_none()
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise Unauthorized("Сессия истекла, войдите заново", code="admin_session_expired")
    admin = await session.get(AdminUser, row.admin_id)
    if admin is None or not admin.is_active:
        raise Unauthorized("Доступ отключён", code="admin_inactive")
    if (now - row.last_seen_at) > timedelta(minutes=1):
        row.last_seen_at = now
    return admin, row


def verify_csrf(token: str, header_value: str | None) -> None:
    if not header_value or not hmac.compare_digest(csrf_for(token), header_value):
        raise Forbidden("CSRF-проверка не пройдена. Обновите страницу", code="csrf_failed")
