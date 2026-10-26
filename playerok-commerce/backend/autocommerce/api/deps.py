from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import User, WebSession
from ..database.session import get_sessionmaker
from ..services import auth
from ..services.audit import Actor
from ..shared.errors import Forbidden, Unauthorized
from .security import SESSION_COOKIE, client_ip, csrf_ok

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


async def db_session() -> AsyncIterator[AsyncSession]:
    """One transaction per request: commit on success, rollback on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


@dataclass
class Context:
    user: User
    web_session: WebSession
    actor: Actor
    session: AsyncSession


async def current(request: Request, session: AsyncSession = Depends(db_session)) -> Context:
    found = await auth.resolve_session(session, request.cookies.get(SESSION_COOKIE))
    if found is None:
        raise Unauthorized("Войдите в панель")
    user, web_session = found
    if request.method in UNSAFE and not csrf_ok(request):
        raise Forbidden("Неверный CSRF-токен. Обновите страницу.", code="csrf")
    return Context(user=user, web_session=web_session, actor=auth.actor_for(user, ip=client_ip(request)), session=session)


def need(permission: str) -> Callable[..., Context]:
    async def checker(ctx: Context = Depends(current)) -> Context:
        auth.require(ctx.actor, permission)
        return ctx

    return checker
