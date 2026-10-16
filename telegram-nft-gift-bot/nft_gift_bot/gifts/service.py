"""Gift listing and owner-confirmed transfers.

Every operation re-checks: active subscription, an active connection that
belongs to the requesting user, the needed Business rights, and that the gift
belongs to that connection. A transfer is a two-step flow
(prepare → explicit confirm) guarded by a compare-and-set status update, so a
double tap or a replayed callback can never execute it twice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.gifts.api import GiftApi, GiftApiError
from nft_gift_bot.gifts.recipient import RecipientRef, ResolvedRecipient
from nft_gift_bot.models import ConnectedAccount, Gift, GiftTransfer, TransferStatus
from nft_gift_bot.repositories import ConnectedAccountRepository, GiftRepository, GiftTransferRepository
from nft_gift_bot.services.crypto import SecretBox
from nft_gift_bot.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class GiftAccessError(Exception):
    """A precondition failed; ``code`` is mapped to a user-facing text in the UI layer."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass
class TransferPreview:
    transfer: GiftTransfer
    gift: Gift
    recipient: ResolvedRecipient


class GiftService:
    def __init__(self, session: AsyncSession, api: GiftApi, box: SecretBox) -> None:
        self._session = session
        self._api = api
        self._box = box
        self._subscriptions = SubscriptionService(session)
        self._accounts = ConnectedAccountRepository(session)
        self._gifts = GiftRepository(session)
        self._transfers = GiftTransferRepository(session)

    async def require_account(self, user_id: int, now: datetime) -> ConnectedAccount:
        if not await self._subscriptions.is_active(user_id, now):
            raise GiftAccessError("no_subscription")
        account = await self._accounts.get_active_for_user(user_id)
        if account is None:
            raise GiftAccessError("no_connection")
        return account

    async def refresh_gifts(self, user_id: int, now: datetime) -> list[Gift]:
        account = await self.require_account(user_id, now)
        if not account.can_view_gifts:
            raise GiftAccessError("no_view_right")
        infos = await self._api.list_owned_gifts(self._box.decrypt(account.connection_id_encrypted))
        seen: set[str] = set()
        for info in infos:
            seen.add(info.owned_gift_id)
            gift = await self._gifts.get_by_owned_id(account.id, info.owned_gift_id)
            if gift is None:
                gift = Gift(connected_account_id=account.id, owned_gift_id=info.owned_gift_id, last_seen_at=now)
                self._gifts.add(gift)
            gift.title = info.title[:255]
            gift.is_unique = info.is_unique
            gift.can_be_transferred = info.can_be_transferred
            gift.transfer_star_count = info.transfer_star_count
            gift.next_transfer_date = info.next_transfer_date
            gift.sticker_file_id = info.sticker_file_id
            gift.last_seen_at = now
        for gift in await self._gifts.list_for_account(account.id):
            if gift.owned_gift_id not in seen:
                await self._gifts.delete(gift)
        await self._session.flush()
        return [g for g in await self._gifts.list_for_account(account.id) if g.owned_gift_id in seen]

    async def cached_gifts(self, user_id: int, now: datetime) -> list[Gift]:
        account = await self.require_account(user_id, now)
        return await self._gifts.list_for_account(account.id)

    async def get_gift(self, user_id: int, gift_id: int, now: datetime) -> Gift:
        account = await self.require_account(user_id, now)
        gift = await self._gifts.get_for_account(account.id, gift_id)
        if gift is None:
            raise GiftAccessError("gift_not_found")
        return gift

    async def find_gifts(self, user_id: int, query: str, now: datetime) -> list[Gift]:
        """Match by local number ("3"), collectible number ("#12") or title substring."""
        gifts = await self.cached_gifts(user_id, now)
        q = query.strip().lower()
        if q.isdigit():
            by_id = [g for g in gifts if g.id == int(q)]
            if by_id:
                return by_id
        return [g for g in gifts if q in g.title.lower()]

    @staticmethod
    def check_transferable(gift: Gift, now: datetime) -> None:
        if not gift.is_unique:
            raise GiftAccessError("not_unique")
        if gift.next_transfer_date is not None and gift.next_transfer_date > now:
            raise GiftAccessError("too_early", gift.next_transfer_date.strftime("%d.%m.%Y %H:%M UTC"))
        if not gift.can_be_transferred:
            raise GiftAccessError("not_transferable")

    async def prepare_transfer(
        self, user_id: int, gift_id: int, recipient: RecipientRef, now: datetime, ttl: timedelta
    ) -> TransferPreview:
        account = await self.require_account(user_id, now)
        if not account.can_transfer_gifts:
            raise GiftAccessError("no_transfer_right")
        gift = await self._gifts.get_for_account(account.id, gift_id)
        if gift is None:
            raise GiftAccessError("gift_not_found")
        self.check_transferable(gift, now)
        star_count = gift.transfer_star_count or None
        if star_count and not account.can_transfer_stars:
            raise GiftAccessError("no_stars_right")
        try:
            resolved = await self._api.resolve_recipient(recipient)
        except GiftApiError as exc:
            raise GiftAccessError("recipient_error", exc.user_message) from exc
        if resolved.chat_id == account.telegram_account_id:
            raise GiftAccessError("self_transfer")
        transfer = GiftTransfer(
            user_id=user_id,
            connected_account_id=account.id,
            owned_gift_id=gift.owned_gift_id,
            gift_title=gift.title,
            recipient_chat_id=resolved.chat_id,
            recipient_label=resolved.label[:64],
            star_count=star_count,
            confirm_expires_at=now + ttl,
        )
        self._transfers.add(transfer)
        await self._session.flush()
        return TransferPreview(transfer=transfer, gift=gift, recipient=resolved)

    async def cancel(self, user_id: int, transfer_id: int) -> bool:
        transfer = await self._transfers.get_for_user(transfer_id, user_id)
        if transfer is None:
            return False
        return await self._transfers.transition(
            transfer.id, TransferStatus.PENDING_CONFIRMATION, TransferStatus.CANCELLED
        )

    async def confirm(self, user_id: int, transfer_id: int, now: datetime) -> GiftTransfer:
        transfer = await self._transfers.get_for_user(transfer_id, user_id)
        if transfer is None:
            raise GiftAccessError("transfer_not_found")
        if transfer.status != TransferStatus.PENDING_CONFIRMATION:
            raise GiftAccessError("already_processed")
        if transfer.confirm_expires_at <= now:
            await self._transfers.transition(
                transfer.id, TransferStatus.PENDING_CONFIRMATION, TransferStatus.EXPIRED
            )
            raise GiftAccessError("confirmation_expired")
        if not await self._transfers.transition(
            transfer.id, TransferStatus.PENDING_CONFIRMATION, TransferStatus.PROCESSING
        ):
            raise GiftAccessError("already_processed")

        try:
            account = await self.require_account(user_id, now)
            if account.id != transfer.connected_account_id or not account.can_transfer_gifts:
                raise GiftAccessError("no_transfer_right")
        except GiftAccessError as exc:
            self._finish(transfer, TransferStatus.FAILED, now, exc.code, None)
            raise

        try:
            await self._api.transfer(
                self._box.decrypt(account.connection_id_encrypted),
                transfer.owned_gift_id,
                transfer.recipient_chat_id,
                transfer.star_count,
            )
        except GiftApiError as exc:
            self._finish(transfer, TransferStatus.FAILED, now, exc.code, exc.user_message)
            logger.warning("gift transfer failed", extra={"transfer_id": transfer.id, "code": exc.code})
            return transfer

        self._finish(transfer, TransferStatus.SUCCEEDED, now, None, None)
        gift = await self._gifts.get_by_owned_id(account.id, transfer.owned_gift_id)
        if gift is not None:
            await self._gifts.delete(gift)
        logger.info("gift transfer succeeded", extra={"transfer_id": transfer.id})
        return transfer

    @staticmethod
    def _finish(transfer: GiftTransfer, status: str, now: datetime, code: str | None, message: str | None) -> None:
        transfer.status = status
        transfer.executed_at = now
        transfer.error_code = code
        transfer.error_message = message[:255] if message else None

    async def history(self, user_id: int, limit: int = 10) -> list[GiftTransfer]:
        return await self._transfers.list_for_user(user_id, limit)

    async def count_succeeded(self, user_id: int) -> int:
        return await self._transfers.count_succeeded_for_user(user_id)
