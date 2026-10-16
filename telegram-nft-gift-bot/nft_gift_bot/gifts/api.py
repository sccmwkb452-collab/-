"""Gift API abstraction. The production implementation is in telegram_api.py."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from nft_gift_bot.gifts.recipient import RecipientRef, ResolvedRecipient


@dataclass(frozen=True)
class OwnedGiftInfo:
    owned_gift_id: str
    title: str
    is_unique: bool
    can_be_transferred: bool
    transfer_star_count: int | None
    next_transfer_date: datetime | None
    sticker_file_id: str | None = None
    # Unique gift slug from its link t.me/nft/<unique_name>, e.g. "PlushPepe-12"
    unique_name: str | None = None


class GiftApiError(Exception):
    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(code)
        self.code = code
        self.user_message = user_message


class GiftApi(Protocol):
    async def list_owned_gifts(self, connection_id: str) -> list[OwnedGiftInfo]: ...

    async def resolve_recipient(self, ref: RecipientRef) -> ResolvedRecipient: ...

    async def transfer(
        self, connection_id: str, owned_gift_id: str, new_owner_chat_id: int, star_count: int | None
    ) -> None: ...
