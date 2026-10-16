from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.connected_account import AccountStatus, ConnectedAccount


class ConnectedAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user(self, user_id: int) -> ConnectedAccount | None:
        result = await self._session.execute(
            select(ConnectedAccount).where(ConnectedAccount.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_pending(self, user_id: int, phone: str) -> ConnectedAccount:
        existing = await self.get_by_user(user_id)
        if existing:
            existing.phone = phone
            existing.status = AccountStatus.PENDING_CODE
            existing.encrypted_session = None
            existing.error_message = None
            existing.connected_at = None
        else:
            existing = ConnectedAccount(
                user_id=user_id,
                phone=phone,
                status=AccountStatus.PENDING_CODE,
            )
            self._session.add(existing)
        await self._session.flush()
        return existing

    async def save(self, account: ConnectedAccount) -> ConnectedAccount:
        self._session.add(account)
        await self._session.flush()
        return account
