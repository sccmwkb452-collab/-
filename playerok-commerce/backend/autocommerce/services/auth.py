"""Users, roles, web sessions, two-factor authentication and Telegram access.

* Passwords: Argon2id. A login attempt for an unknown e-mail still spends the
  same time on hashing, so the answer does not reveal which e-mails exist.
* Sessions: a random token in an httpOnly cookie, only its keyed hash in the
  database; idle and absolute expiry; revocation per session or for all.
* Lockout: after ``login_max_attempts`` failures the account is locked for
  ``login_lock_minutes``.
* Telegram: the bot serves only owner IDs from the environment and users
  linked through a one-time code from the web panel.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import RoleCode
from ..database.models import OneTimeToken, Role, User, WebSession
from ..shared import crypto
from ..shared.errors import Conflict, DomainError, Forbidden, NotFound, Unauthorized
from ..shared.timeutil import utcnow
from .audit import Actor, audit

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

ALL_PERMISSIONS: dict[str, str] = {
    "view": "Просмотр разделов",
    "orders.manage": "Управление заказами",
    "orders.reveal_codes": "Просмотр выданных кодов",
    "products.manage": "Товары и категории",
    "pricing.manage": "Цены и правила прибыльности",
    "listings.manage": "Подготовка объявлений",
    "listings.publish": "Публикация объявлений",
    "suppliers.manage": "Поставщики и ключи",
    "suppliers.purchase": "Закупка у поставщиков",
    "inventory.manage": "Склад и коды",
    "messages.manage": "Сообщения покупателей",
    "autosettings.manage": "Автонастройки",
    "analytics.export": "Экспорт аналитики",
    "security.manage": "Безопасность и аварийная остановка",
    "users.manage": "Пользователи и роли",
    "settings.manage": "Настройки системы",
}

ROLE_PERMISSIONS: dict[RoleCode, list[str]] = {
    RoleCode.OWNER: ["*"],
    RoleCode.ADMIN: [p for p in ALL_PERMISSIONS if p != "users.manage"],
    RoleCode.OPERATOR: [
        "view",
        "orders.manage",
        "orders.reveal_codes",
        "listings.manage",
        "inventory.manage",
        "messages.manage",
        "analytics.export",
    ],
    RoleCode.VIEWER: ["view"],
}

ROLE_NAMES: dict[RoleCode, str] = {
    RoleCode.OWNER: "Владелец",
    RoleCode.ADMIN: "Администратор",
    RoleCode.OPERATOR: "Оператор",
    RoleCode.VIEWER: "Наблюдатель",
}


# --- passwords -------------------------------------------------------------


def validate_password(password: str) -> None:
    if len(password) < 10:
        raise DomainError("Пароль должен быть не короче 10 символов")
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        raise DomainError("Пароль должен содержать строчные и заглавные буквы и цифру")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# --- roles -------------------------------------------------------------------


async def ensure_roles(session: AsyncSession) -> dict[RoleCode, Role]:
    existing = {r.code: r for r in (await session.execute(select(Role))).scalars()}
    for code, perms in ROLE_PERMISSIONS.items():
        role = existing.get(code)
        if role is None:
            role = Role(code=code, name=ROLE_NAMES[code], permissions=perms)
            session.add(role)
            existing[code] = role
        else:
            role.permissions = perms
            role.name = ROLE_NAMES[code]
    await session.flush()
    return existing


def permissions_of(user: User) -> frozenset[str]:
    return frozenset(user.role.permissions or [])


def actor_for(user: User, *, kind: str = "web", ip: str | None = None) -> Actor:
    return Actor(type=kind, id=str(user.id), name=user.display_name, ip=ip, user_id=user.id, permissions=permissions_of(user))


def require(actor: Actor, permission: str) -> None:
    if not actor.can(permission):
        raise Forbidden(f"Недостаточно прав: {ALL_PERMISSIONS.get(permission, permission)}")


# --- users -------------------------------------------------------------------


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    role: RoleCode,
    actor: Actor,
    telegram_id: int | None = None,
) -> User:
    email = email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise DomainError("Укажите корректный e-mail")
    validate_password(password)
    if (await session.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
        raise Conflict("Пользователь с таким e-mail уже есть")
    roles = await ensure_roles(session)
    user = User(
        email=email,
        display_name=display_name.strip()[:120] or email,
        password_hash=hash_password(password),
        role_id=roles[role].id,
        telegram_id=telegram_id,
        password_changed_at=utcnow(),
    )
    session.add(user)
    await session.flush()
    await session.refresh(user, ["role"])
    await audit(session, actor, "user.create", entity_type="user", entity_id=user.id, details={"email": email, "role": role.value})
    return user


async def set_password(session: AsyncSession, user: User, new_password: str, actor: Actor, *, revoke_sessions: bool = True) -> None:
    validate_password(new_password)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.failed_logins = 0
    user.locked_until = None
    if revoke_sessions:
        await revoke_all_sessions(session, user.id)
    await audit(session, actor, "user.password_change", entity_type="user", entity_id=user.id)


@dataclass
class LoginResult:
    user: User
    token: str
    session: WebSession


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    totp_code: str | None,
    ip: str | None,
    user_agent: str | None,
) -> LoginResult:
    settings = get_settings()
    email = email.strip().lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    now = utcnow()
    if user is None:
        verify_password(_DUMMY_HASH, password)
        await audit(session, Actor(type="web", ip=ip, name=email[:120]), "auth.login_failed", details={"reason": "unknown_email"})
        raise Unauthorized("Неверный e-mail или пароль")
    if user.locked_until and user.locked_until > now:
        verify_password(_DUMMY_HASH, password)
        raise Unauthorized("Вход временно заблокирован после нескольких неудачных попыток. Попробуйте позже.", code="locked")
    if not user.is_active or not verify_password(user.password_hash, password):
        user.failed_logins += 1
        if user.failed_logins >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_logins = 0
        await audit(session, actor_for(user, ip=ip), "auth.login_failed", entity_type="user", entity_id=user.id)
        raise Unauthorized("Неверный e-mail или пароль")
    if user.totp_enabled:
        if not totp_code:
            raise Unauthorized("Введите код из приложения-аутентификатора", code="totp_required")
        if not verify_totp(user, totp_code):
            user.failed_logins += 1
            await audit(session, actor_for(user, ip=ip), "auth.totp_failed", entity_type="user", entity_id=user.id)
            raise Unauthorized("Неверный код двухфакторной аутентификации", code="totp_invalid")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    token = secrets.token_urlsafe(32)
    web_session = WebSession(
        user_id=user.id,
        token_hash=crypto.token_hash(token),
        ip=ip,
        user_agent=(user_agent or "")[:300],
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_hours),
    )
    session.add(web_session)
    await session.flush()
    await audit(session, actor_for(user, ip=ip), "auth.login", entity_type="user", entity_id=user.id)
    return LoginResult(user=user, token=token, session=web_session)


async def resolve_session(session: AsyncSession, token: str | None) -> tuple[User, WebSession] | None:
    if not token or len(token) > 200:
        return None
    settings = get_settings()
    row = (await session.execute(select(WebSession).where(WebSession.token_hash == crypto.token_hash(token)))).scalar_one_or_none()
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    if row.last_seen_at + timedelta(minutes=settings.session_idle_minutes) <= now:
        row.revoked_at = now
        return None
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    if (now - row.last_seen_at).total_seconds() > 60:
        row.last_seen_at = now
    return user, row


async def logout(session: AsyncSession, web_session: WebSession) -> None:
    web_session.revoked_at = utcnow()


async def revoke_all_sessions(session: AsyncSession, user_id: int, *, except_id: int | None = None) -> int:
    stmt = update(WebSession).where(WebSession.user_id == user_id, WebSession.revoked_at.is_(None))
    if except_id is not None:
        stmt = stmt.where(WebSession.id != except_id)
    result = await session.execute(stmt.values(revoked_at=utcnow()))
    return result.rowcount or 0


# --- two-factor authentication ------------------------------------------------


def verify_totp(user: User, code: str) -> bool:
    if not user.totp_secret_enc:
        return False
    secret = crypto.decrypt(user.totp_secret_enc)
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


async def start_totp_setup(session: AsyncSession, user: User) -> str:
    """Generate a secret (not yet enabled). Returns the otpauth:// URI."""
    secret = pyotp.random_base32()
    user.totp_secret_enc = crypto.encrypt(secret)
    user.totp_enabled = False
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="PlayerOK Auto Commerce")


async def confirm_totp(session: AsyncSession, user: User, code: str, actor: Actor) -> None:
    if not verify_totp(user, code):
        raise DomainError("Код не подошёл. Проверьте время на телефоне и попробуйте снова.")
    user.totp_enabled = True
    await audit(session, actor, "user.totp_enabled", entity_type="user", entity_id=user.id)


async def disable_totp(session: AsyncSession, user: User, password: str, actor: Actor) -> None:
    if not verify_password(user.password_hash, password):
        raise Unauthorized("Неверный пароль")
    user.totp_enabled = False
    user.totp_secret_enc = None
    await audit(session, actor, "user.totp_disabled", entity_type="user", entity_id=user.id)


# --- Telegram access -------------------------------------------------------------


async def telegram_actor(session: AsyncSession, telegram_id: int, name: str | None) -> Actor | None:
    """Actor for a Telegram user, or None when the user has no access."""
    user = (await session.execute(select(User).where(User.telegram_id == telegram_id, User.is_active.is_(True)))).scalar_one_or_none()
    if user is not None:
        return actor_for(user, kind="telegram")
    if telegram_id in get_settings().owner_telegram_ids:
        return Actor(type="telegram", id=str(telegram_id), name=name or str(telegram_id), permissions=frozenset({"*"}))
    return None


async def create_link_code(session: AsyncSession, user: User, actor: Actor) -> str:
    """One-time code that links a Telegram account to a web user (/start <code>)."""
    code = secrets.token_urlsafe(12)
    session.add(
        OneTimeToken(
            purpose="telegram_link", token_hash=crypto.token_hash(code), user_id=user.id, expires_at=utcnow() + timedelta(minutes=15)
        )
    )
    await audit(session, actor, "user.telegram_link_code", entity_type="user", entity_id=user.id)
    return code


async def redeem_link_code(session: AsyncSession, code: str, telegram_id: int) -> User:
    row = (
        await session.execute(
            select(OneTimeToken)
            .where(OneTimeToken.token_hash == crypto.token_hash(code), OneTimeToken.purpose == "telegram_link")
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow() or row.user_id is None:
        raise NotFound("Код привязки недействителен или устарел. Получите новый в веб-панели.")
    taken = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if taken is not None and taken.id != row.user_id:
        raise Conflict("Этот Telegram-аккаунт уже привязан к другому пользователю")
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Forbidden("Пользователь отключён")
    user.telegram_id = telegram_id
    row.used_at = utcnow()
    await audit(session, actor_for(user, kind="telegram"), "user.telegram_linked", entity_type="user", entity_id=user.id)
    return user


async def owner_chat_ids(session: AsyncSession, permission: str | None = None) -> list[int]:
    """Telegram chats that receive notifications: env owners + linked active users
    (filtered by permission when given)."""
    ids = set(get_settings().owner_telegram_ids)
    users = (await session.execute(select(User).where(User.telegram_id.is_not(None), User.is_active.is_(True)))).scalars().all()
    for user in users:
        perms = permissions_of(user)
        if permission is None or "*" in perms or permission in perms:
            ids.add(int(user.telegram_id))
    return sorted(ids)
