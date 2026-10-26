from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...database.models import WebSession
from ...services import auth
from ...shared.errors import NotFound
from .. import serializers as ser
from ..deps import Context, current, db_session
from ..security import CSRF_COOKIE, SESSION_COOKIE, client_ip, csrf_token_for, limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    totp: str | None = Field(default=None, max_length=12)


def _set_cookies(response: Response, token: str) -> str:
    s = get_settings()
    max_age = s.session_hours * 3600
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=s.cookie_secure, samesite="strict", path="/")
    csrf = csrf_token_for(token)
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=s.cookie_secure, samesite="strict", path="/")
    return csrf


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, session: AsyncSession = Depends(db_session)) -> dict:
    ip = client_ip(request)
    limiter.check(f"login:ip:{ip}", 10, 60)
    limiter.check(f"login:email:{body.email.lower()}", 8, 900)
    try:
        result = await auth.login(
            session, email=body.email, password=body.password, totp_code=body.totp, ip=ip, user_agent=request.headers.get("user-agent")
        )
    except Exception:
        await session.commit()  # keep the failed-attempt counter and the audit record
        raise
    csrf = _set_cookies(response, result.token)
    return {"user": ser.user(result.user), "csrf": csrf}


@router.post("/logout")
async def logout(response: Response, ctx: Context = Depends(current)) -> dict:
    await auth.logout(ctx.session, ctx.web_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(ctx: Context = Depends(current)) -> dict:
    return {"user": ser.user(ctx.user), "bot_username": get_settings().bot_username}


class PasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@router.post("/password")
async def change_password(body: PasswordIn, ctx: Context = Depends(current)) -> dict:
    from ...shared.errors import Unauthorized

    if not auth.verify_password(ctx.user.password_hash, body.current_password):
        raise Unauthorized("Неверный текущий пароль", code="wrong_password")
    await auth.set_password(ctx.session, ctx.user, body.new_password, ctx.actor, revoke_sessions=False)
    revoked = await auth.revoke_all_sessions(ctx.session, ctx.user.id, except_id=ctx.web_session.id)
    return {"ok": True, "revoked_sessions": revoked}


@router.post("/totp/setup")
async def totp_setup(ctx: Context = Depends(current)) -> dict:
    uri = await auth.start_totp_setup(ctx.session, ctx.user)
    return {"otpauth_uri": uri}


class CodeIn(BaseModel):
    code: str = Field(max_length=12)


@router.post("/totp/confirm")
async def totp_confirm(body: CodeIn, ctx: Context = Depends(current)) -> dict:
    await auth.confirm_totp(ctx.session, ctx.user, body.code, ctx.actor)
    return {"ok": True}


class DisableTotpIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/totp/disable")
async def totp_disable(body: DisableTotpIn, ctx: Context = Depends(current)) -> dict:
    await auth.disable_totp(ctx.session, ctx.user, body.password, ctx.actor)
    return {"ok": True}


@router.get("/sessions")
async def sessions(ctx: Context = Depends(current)) -> dict:
    rows = (
        await ctx.session.execute(
            select(WebSession)
            .where(WebSession.user_id == ctx.user.id, WebSession.revoked_at.is_(None))
            .order_by(WebSession.last_seen_at.desc())
        )
    ).scalars()
    return {
        "items": [
            {
                "id": s.id,
                "ip": s.ip,
                "user_agent": s.user_agent,
                "created_at": ser.dt(s.created_at),
                "last_seen_at": ser.dt(s.last_seen_at),
                "expires_at": ser.dt(s.expires_at),
                "current": s.id == ctx.web_session.id,
            }
            for s in rows
        ]
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: int, ctx: Context = Depends(current)) -> dict:
    row = await ctx.session.get(WebSession, session_id)
    if row is None or row.user_id != ctx.user.id:
        raise NotFound("Сессия не найдена")
    await auth.logout(ctx.session, row)
    return {"ok": True}


@router.post("/sessions/revoke-others")
async def revoke_others(ctx: Context = Depends(current)) -> dict:
    return {"revoked": await auth.revoke_all_sessions(ctx.session, ctx.user.id, except_id=ctx.web_session.id)}


@router.post("/telegram-link")
async def telegram_link(ctx: Context = Depends(current)) -> dict:
    code = await auth.create_link_code(ctx.session, ctx.user, ctx.actor)
    bot = get_settings().bot_username
    return {
        "code": code,
        "link": f"https://t.me/{bot}?start=link_{code}" if bot else None,
        "command": f"/start link_{code}",
        "expires_minutes": 15,
    }
