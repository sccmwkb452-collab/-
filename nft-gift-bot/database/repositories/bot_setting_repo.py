from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.bot_setting import BotSetting


class BotSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> str | None:
        result = await self._session.execute(
            select(BotSetting.value).where(BotSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def set(self, key: str, value: str) -> None:
        existing = await self._session.get(BotSetting, key)
        if existing:
            existing.value = value
        else:
            self._session.add(BotSetting(key=key, value=value))
        await self._session.flush()
