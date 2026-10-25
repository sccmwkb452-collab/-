from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(url: str, **kwargs) -> AsyncEngine:
    # hide_parameters: SQL errors must not print item contents into logs
    return create_async_engine(url, pool_pre_ping=True, hide_parameters=True, **kwargs)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
