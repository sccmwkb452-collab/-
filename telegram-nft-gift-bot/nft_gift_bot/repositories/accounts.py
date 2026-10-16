from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import ConnectedAccount, ConnectionStatus


class ConnectedAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_lookup_hash(self, lookup_hash: str) -> ConnectedAccount | None:
        return await self.session.scalar(
            select(ConnectedAccount).where(ConnectedAccount.connection_lookup_hash == lookup_hash)
        )

    async def get_active_for_user(self, user_id: int) -> ConnectedAccount | None:
        return await self.session.scalar(
            select(ConnectedAccount)
            .where(ConnectedAccount.user_id == user_id, ConnectedAccount.status == ConnectionStatus.ACTIVE)
            .order_by(ConnectedAccount.id.desc())
        )

    async def get_latest_for_user(self, user_id: int) -> ConnectedAccount | None:
        return await self.session.scalar(
            select(ConnectedAccount)
            .where(ConnectedAccount.user_id == user_id)
            .order_by(ConnectedAccount.id.desc())
        )

    async def list_active_for_user(self, user_id: int) -> list[ConnectedAccount]:
        result = await self.session.scalars(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == user_id, ConnectedAccount.status == ConnectionStatus.ACTIVE
            )
        )
        return list(result)

    def add(self, account: ConnectedAccount) -> None:
        self.session.add(account)

    async def count_active(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count(ConnectedAccount.id)).where(ConnectedAccount.status == ConnectionStatus.ACTIVE)
            )
            or 0
        )
