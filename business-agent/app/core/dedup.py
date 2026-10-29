"""Идемпотентная обработка обновлений: одно обновление Telegram обрабатывается один раз."""
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ProcessedUpdate, utcnow


async def claim_update(factory: async_sessionmaker[AsyncSession], key: str) -> bool:
    """True — обновление новое и закреплено за нами; False — уже обрабатывалось."""
    async with factory() as session:
        session.add(ProcessedUpdate(key=key))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
    return True


async def purge_old(session: AsyncSession, days: int = 3) -> int:
    res = await session.execute(delete(ProcessedUpdate).where(ProcessedUpdate.created_at < utcnow() - timedelta(days=days)))
    return res.rowcount or 0
