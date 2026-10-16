"""Business logic for ConnectedAccount — encryption, status, disconnect."""
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models.connected_account import AccountStatus, ConnectedAccount
from database.repositories.account_repo import ConnectedAccountRepository
from services.crypto_service import decrypt_session, encrypt_session

logger = logging.getLogger(__name__)


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ConnectedAccountRepository(session)

    async def get(self, user_id: int) -> ConnectedAccount | None:
        return await self._repo.get_by_user(user_id)

    async def start_auth(self, user_id: int, phone: str) -> ConnectedAccount:
        return await self._repo.upsert_pending(user_id, phone)

    async def mark_pending_2fa(self, account: ConnectedAccount) -> ConnectedAccount:
        account.status = AccountStatus.PENDING_2FA
        return await self._repo.save(account)

    async def save_session(
        self, account: ConnectedAccount, session_string: str
    ) -> ConnectedAccount:
        if not settings.account_encryption_key:
            raise RuntimeError("ACCOUNT_ENCRYPTION_KEY is not set — cannot store session securely")
        account.encrypted_session = encrypt_session(session_string, settings.account_encryption_key)
        account.status = AccountStatus.CONNECTED
        account.connected_at = datetime.now(tz=timezone.utc)
        account.error_message = None
        logger.info("Session saved (encrypted) for user_id=%d", account.user_id)
        return await self._repo.save(account)

    async def set_error(self, account: ConnectedAccount, message: str) -> ConnectedAccount:
        account.status = AccountStatus.ERROR
        account.error_message = message[:256]
        account.encrypted_session = None
        return await self._repo.save(account)

    async def disconnect(self, account: ConnectedAccount) -> ConnectedAccount:
        account.status = AccountStatus.DISCONNECTED
        account.encrypted_session = None
        account.connected_at = None
        account.error_message = None
        logger.info("Account disconnected for user_id=%d", account.user_id)
        return await self._repo.save(account)

    def get_decrypted_session(self, account: ConnectedAccount) -> str | None:
        if not account.encrypted_session or not settings.account_encryption_key:
            return None
        try:
            return decrypt_session(account.encrypted_session, settings.account_encryption_key)
        except Exception:
            logger.exception("Failed to decrypt session for user_id=%d", account.user_id)
            return None
