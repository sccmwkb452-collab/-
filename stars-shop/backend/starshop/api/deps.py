from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import AdminRole
from ..database.models import AdminSession, AdminUser, User
from ..database.session import get_sessionmaker
from ..services.admin_auth import resolve_session, verify_csrf
from ..services.app_settings import RuntimeSettings, load_runtime_settings
from ..services.audit import RequestMeta
from ..services.users import upsert_telegram_user
from ..shared.demo_identity import demo_init_data, is_demo_user_id
from ..shared.errors import Forbidden, Unauthorized
from ..shared.telegram_auth import InitData, validate_init_data
from .ratelimit import get_limiter

ADMIN_COOKIE = "admin_session"


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_runtime(session: SessionDep) -> RuntimeSettings:
    return await load_runtime_settings(session)


RuntimeDep = Annotated[RuntimeSettings, Depends(get_runtime)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def request_meta(request: Request) -> RequestMeta:
    return RequestMeta(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


def parse_tma_header(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "tma" else ""


async def get_init_data(authorization: Annotated[str | None, Header()] = None) -> InitData:
    settings = get_settings()
    scheme, _, key = (authorization or "").partition(" ")
    if settings.public_demo and scheme.lower() == "demo":
        return demo_init_data(key.strip(), settings.secret_key.get_secret_value())
    return validate_init_data(
        parse_tma_header(authorization),
        settings.bot_token.get_secret_value(),
        max_age_seconds=settings.init_data_max_age_seconds,
    )


InitDataDep = Annotated[InitData, Depends(get_init_data)]


async def current_user(init: InitDataDep, session: SessionDep, runtime: RuntimeDep, request: Request) -> User:
    if is_demo_user_id(init.user.id) and runtime.shop.mode != "demo":
        raise Unauthorized("Откройте магазин из Telegram", code="demo_identity_disabled")
    track = request.url.path.endswith("/me")
    user, created = await upsert_telegram_user(session, init.user, runtime=runtime, start_param=init.start_param, track_activity=track)
    if created or track:
        await session.commit()
    return user


UserDep = Annotated[User, Depends(current_user)]


def user_rate_limit(name: str, limit: int, window: int = 60) -> Callable:
    async def dependency(init: InitDataDep) -> None:
        await get_limiter().check(f"{name}:u{init.user.id}", limit, window)

    return dependency


def ip_rate_limit(name: str, limit: int, window: int = 60) -> Callable:
    async def dependency(request: Request) -> None:
        await get_limiter().check(f"{name}:ip{client_ip(request)}", limit, window)

    return dependency


# --- admin --------------------------------------------------------------------

ROLE_RANK = {AdminRole.support: 1, AdminRole.manager: 2, AdminRole.owner: 3}


class AdminContext:
    def __init__(self, admin: AdminUser, session_row: AdminSession, meta: RequestMeta):
        self.admin = admin
        self.session_row = session_row
        self.meta = meta

    def require(self, role: AdminRole) -> None:
        if ROLE_RANK[AdminRole(self.admin.role)] < ROLE_RANK[role]:
            raise Forbidden("Недостаточно прав для этого действия", code="admin_forbidden")


async def _admin_context(request: Request, session: SessionDep) -> AdminContext:
    token = request.cookies.get(ADMIN_COOKIE)
    admin, row = await resolve_session(session, token)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        verify_csrf(token or "", request.headers.get("x-csrf-token"))
    return AdminContext(admin, row, request_meta(request))


def require_admin(role: AdminRole = AdminRole.support) -> Callable:
    async def dependency(ctx: Annotated[AdminContext, Depends(_admin_context)]) -> AdminContext:
        ctx.require(role)
        return ctx

    return dependency


SupportAdmin = Annotated[AdminContext, Depends(require_admin(AdminRole.support))]
ManagerAdmin = Annotated[AdminContext, Depends(require_admin(AdminRole.manager))]
OwnerAdmin = Annotated[AdminContext, Depends(require_admin(AdminRole.owner))]
