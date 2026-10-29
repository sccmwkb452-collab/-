from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str, **kwargs) -> async_sessionmaker[AsyncSession]:
    """Создаёт движок и фабрику сессий. Вызывается один раз при старте (и в тестах)."""
    global _engine, _factory
    if url.startswith("postgresql"):
        kwargs.setdefault("pool_size", 10)
        kwargs.setdefault("max_overflow", 20)
        kwargs.setdefault("pool_pre_ping", True)
    _engine = create_async_engine(url, **kwargs)
    _factory = async_sessionmaker(_engine, expire_on_commit=False, autoflush=False)
    return _factory


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _factory is None:
        raise RuntimeError("init_engine() ещё не вызван")
    return _factory


async def create_schema() -> None:
    """Создаёт недостающие таблицы (идемпотентно)."""
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()
