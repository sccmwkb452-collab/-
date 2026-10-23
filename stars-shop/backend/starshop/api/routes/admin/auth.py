from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ....config import get_settings
from ....services import admin_auth, audit
from ....shared.errors import Forbidden
from ....shared.telegram_auth import validate_init_data, validate_login_widget
from ....shared.timeutil import utcnow
from ...deps import ADMIN_COOKIE, SessionDep, SupportAdmin, ip_rate_limit, request_meta
from ...schemas import InitDataIn, LoginTokenIn, LoginWidgetIn
from ...serializers import admin_user

router = APIRouter(prefix="/auth")


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=settings.admin_session_hours * 3600,
        httponly=True,
        secure=settings.is_production_env or settings.public_base_url.startswith("https://"),
        samesite="strict",
        path="/api/v1/admin",
    )


async def _login(session, admin, request: Request, response: Response, method: str) -> dict:
    meta = request_meta(request)
    issued = await admin_auth.start_session(session, admin, ip=meta.ip, user_agent=meta.user_agent)
    await audit.record(session, admin, "admin.login", entity_type="admin", entity_id=admin.id, summary=f"Вход: {method}", meta=meta)
    await session.commit()
    _set_cookie(response, issued.token)
    return {"admin": admin_user(admin), "csrf_token": issued.csrf}


@router.post("/exchange", dependencies=[Depends(ip_rate_limit("admin_login", 10))])
async def exchange(body: LoginTokenIn, request: Request, response: Response, session: SessionDep) -> dict:
    admin = await admin_auth.consume_login_token(session, body.token)
    return await _login(session, admin, request, response, "одноразовая ссылка из бота")


@router.post("/webapp", dependencies=[Depends(ip_rate_limit("admin_login", 10))])
async def webapp_login(body: InitDataIn, request: Request, response: Response, session: SessionDep) -> dict:
    s = get_settings()
    init = validate_init_data(body.init_data, s.bot_token.get_secret_value(), max_age_seconds=3600)
    admin = await admin_auth.admin_by_telegram_id(session, init.user.id)
    if admin is None:
        raise Forbidden("Этот аккаунт Telegram не является администратором", code="not_admin")
    return await _login(session, admin, request, response, "Telegram Mini App")


@router.post("/telegram-widget", dependencies=[Depends(ip_rate_limit("admin_login", 10))])
async def widget_login(body: LoginWidgetIn, request: Request, response: Response, session: SessionDep) -> dict:
    s = get_settings()
    tg = validate_login_widget(body.model_dump(), s.bot_token.get_secret_value(), max_age_seconds=600)
    admin = await admin_auth.admin_by_telegram_id(session, tg.id)
    if admin is None:
        raise Forbidden("Этот аккаунт Telegram не является администратором", code="not_admin")
    return await _login(session, admin, request, response, "Telegram Login Widget")


@router.get("/me")
async def me(ctx: SupportAdmin, request: Request, session: SessionDep) -> dict:
    await session.commit()  # persists last_seen_at
    token = request.cookies.get(ADMIN_COOKIE, "")
    return {"admin": admin_user(ctx.admin), "csrf_token": admin_auth.csrf_for(token), "bot_username": get_settings().bot_username or None}


@router.post("/logout")
async def logout(ctx: SupportAdmin, response: Response, session: SessionDep) -> dict:
    ctx.session_row.revoked_at = utcnow()
    await audit.record(session, ctx.admin, "admin.logout", entity_type="admin", entity_id=ctx.admin.id, meta=ctx.meta)
    await session.commit()
    response.delete_cookie(ADMIN_COOKIE, path="/api/v1/admin")
    return {"ok": True}
