from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import AdminAction, BotSettings


class AdminActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, admin_telegram_id: int, action: str, target: str | None, details: dict[str, Any] | None) -> None:
        self.session.add(
            AdminAction(admin_telegram_id=admin_telegram_id, action=action, target=target, details=details)
        )

    async def list_recent(self, limit: int = 20) -> list[AdminAction]:
        result = await self.session.scalars(select(AdminAction).order_by(AdminAction.id.desc()).limit(limit))
        return list(result)


class BotSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        row = await self.session.get(BotSettings, key)
        return row.value if row else None

    async def set(self, key: str, value: str, updated_by: int | None) -> None:
        row = await self.session.get(BotSettings, key)
        if row is None:
            self.session.add(BotSettings(key=key, value=value, updated_by=updated_by))
        else:
            row.value = value
            row.updated_by = updated_by

    async def list_prefix(self, prefix: str) -> dict[str, str]:
        result = await self.session.scalars(select(BotSettings).where(BotSettings.key.startswith(prefix)))
        return {row.key: row.value for row in result}
