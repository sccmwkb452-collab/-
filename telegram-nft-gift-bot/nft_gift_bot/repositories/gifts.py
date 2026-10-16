from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import Gift, GiftTransfer, TransferStatus


class GiftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_account(self, account_id: int, gift_id: int) -> Gift | None:
        return await self.session.scalar(
            select(Gift).where(Gift.id == gift_id, Gift.connected_account_id == account_id)
        )

    async def get_by_owned_id(self, account_id: int, owned_gift_id: str) -> Gift | None:
        return await self.session.scalar(
            select(Gift).where(Gift.connected_account_id == account_id, Gift.owned_gift_id == owned_gift_id)
        )

    async def list_for_account(self, account_id: int) -> list[Gift]:
        result = await self.session.scalars(
            select(Gift).where(Gift.connected_account_id == account_id).order_by(Gift.id)
        )
        return list(result)

    def add(self, gift: Gift) -> None:
        self.session.add(gift)

    async def delete(self, gift: Gift) -> None:
        await self.session.delete(gift)


class GiftTransferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, transfer: GiftTransfer) -> None:
        self.session.add(transfer)

    async def get_for_user(self, transfer_id: int, user_id: int) -> GiftTransfer | None:
        return await self.session.scalar(
            select(GiftTransfer).where(GiftTransfer.id == transfer_id, GiftTransfer.user_id == user_id)
        )

    async def transition(self, transfer_id: int, from_status: str, to_status: str) -> bool:
        """Compare-and-set on status: guarantees a transfer is executed at most once."""
        result = await self.session.execute(
            update(GiftTransfer)
            .where(GiftTransfer.id == transfer_id, GiftTransfer.status == from_status)
            .values(status=to_status)
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount == 1

    async def list_for_user(self, user_id: int, limit: int = 10) -> list[GiftTransfer]:
        result = await self.session.scalars(
            select(GiftTransfer)
            .where(GiftTransfer.user_id == user_id)
            .order_by(GiftTransfer.id.desc())
            .limit(limit)
        )
        return list(result)

    async def list_recent(self, limit: int = 20) -> list[GiftTransfer]:
        result = await self.session.scalars(select(GiftTransfer).order_by(GiftTransfer.id.desc()).limit(limit))
        return list(result)

    async def count_succeeded_for_user(self, user_id: int) -> int:
        return int(
            await self.session.scalar(
                select(func.count(GiftTransfer.id)).where(
                    GiftTransfer.user_id == user_id, GiftTransfer.status == TransferStatus.SUCCEEDED
                )
            )
            or 0
        )
