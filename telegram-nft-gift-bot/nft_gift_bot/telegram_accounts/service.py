"""Connecting the owner's own Telegram account via Telegram Business.

The only official way for a bot to act on a user account is a Business
connection: the owner opens Telegram → Settings → Telegram Business →
Chatbots, adds this bot and picks the rights. Telegram then sends a
``business_connection`` update. No login codes, cloud passwords or session
files ever pass through the bot.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import ConnectedAccount, ConnectionStatus, User
from nft_gift_bot.repositories import ConnectedAccountRepository, UserRepository
from nft_gift_bot.services.crypto import SecretBox
from nft_gift_bot.services.subscription_service import SubscriptionService


@dataclass(frozen=True)
class BusinessConnectionEvent:
    connection_id: str
    owner_telegram_id: int
    is_enabled: bool
    can_view_gifts: bool
    can_transfer_gifts: bool
    can_transfer_stars: bool


class ConnectionOutcome(StrEnum):
    CONNECTED = "connected"
    UPDATED = "updated"
    DISABLED = "disabled"
    UNKNOWN_USER = "unknown_user"
    NO_SUBSCRIPTION = "no_subscription"


@dataclass
class ConnectionResult:
    outcome: ConnectionOutcome
    user: User | None = None
    account: ConnectedAccount | None = None


class AccountConnectionService:
    def __init__(self, session: AsyncSession, box: SecretBox) -> None:
        self._repo = ConnectedAccountRepository(session)
        self._users = UserRepository(session)
        self._subscriptions = SubscriptionService(session)
        self._box = box

    async def handle_event(self, event: BusinessConnectionEvent, now: datetime) -> ConnectionResult:
        lookup = self._box.lookup_hash(event.connection_id)
        account = await self._repo.get_by_lookup_hash(lookup)
        # The owner is whoever Telegram says made the connection, never user input.
        user = await self._users.get_by_telegram_id(event.owner_telegram_id)

        if account is None:
            if not event.is_enabled:
                return ConnectionResult(ConnectionOutcome.DISABLED, user)
            if user is None:
                return ConnectionResult(ConnectionOutcome.UNKNOWN_USER)
            if not await self._subscriptions.is_active(user.id, now):
                return ConnectionResult(ConnectionOutcome.NO_SUBSCRIPTION, user)
            for other in await self._repo.list_active_for_user(user.id):
                other.status = ConnectionStatus.DISABLED
                other.disconnected_at = now
            account = ConnectedAccount(
                user_id=user.id,
                connection_lookup_hash=lookup,
                connection_id_encrypted=self._box.encrypt(event.connection_id),
                telegram_account_id=event.owner_telegram_id,
                connected_at=now,
            )
            self._apply_rights(account, event)
            self._repo.add(account)
            return ConnectionResult(ConnectionOutcome.CONNECTED, user, account)

        if account.telegram_account_id != event.owner_telegram_id:
            # Should never happen; refuse to let a connection change hands.
            account.status = ConnectionStatus.DISABLED
            account.disconnected_at = now
            return ConnectionResult(ConnectionOutcome.DISABLED, user, account)

        self._apply_rights(account, event)
        if event.is_enabled:
            account.status = ConnectionStatus.ACTIVE
            account.disconnected_at = None
            return ConnectionResult(ConnectionOutcome.UPDATED, user, account)
        account.status = ConnectionStatus.DISABLED
        account.disconnected_at = now
        return ConnectionResult(ConnectionOutcome.DISABLED, user, account)

    @staticmethod
    def _apply_rights(account: ConnectedAccount, event: BusinessConnectionEvent) -> None:
        account.can_view_gifts = event.can_view_gifts
        account.can_transfer_gifts = event.can_transfer_gifts
        account.can_transfer_stars = event.can_transfer_stars

    async def revoke(self, user_id: int, now: datetime) -> bool:
        """Owner-initiated disconnect: forget the encrypted connection ID entirely.

        A bot cannot remove itself from the owner's Business settings, so the UI
        also tells the owner to remove it there; until then any update for that
        connection is treated as a brand new connection request.
        """
        revoked = False
        for account in await self._repo.list_active_for_user(user_id):
            account.status = ConnectionStatus.REVOKED
            account.disconnected_at = now
            account.connection_id_encrypted = ""
            account.connection_lookup_hash = f"revoked:{account.id}:{secrets.token_hex(16)}"
            revoked = True
        return revoked

    async def get_active(self, user_id: int) -> ConnectedAccount | None:
        return await self._repo.get_active_for_user(user_id)

    async def get_latest(self, user_id: int) -> ConnectedAccount | None:
        return await self._repo.get_latest_for_user(user_id)

    async def set_notify(self, user_id: int, enabled: bool) -> bool:
        account = await self._repo.get_active_for_user(user_id)
        if account is None:
            return False
        account.notify_new_gifts = enabled
        return True

    def connection_id(self, account: ConnectedAccount) -> str:
        return self._box.decrypt(account.connection_id_encrypted)
