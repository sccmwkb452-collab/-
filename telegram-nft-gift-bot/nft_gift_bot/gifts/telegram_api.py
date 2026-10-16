"""Telegram Bot API implementation of GiftApi.

Uses only documented Business methods:
* getBusinessAccountGifts — needs the ``can_view_gifts_and_stars`` right;
* transferGift — unique gifts only, needs ``can_transfer_and_upgrade_gifts``
  (and ``can_transfer_stars`` when the transfer has a Stars fee).
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import OwnedGiftRegular, OwnedGiftUnique

from nft_gift_bot.gifts.api import GiftApiError, OwnedGiftInfo
from nft_gift_bot.gifts.recipient import RecipientRef, ResolvedRecipient

PAGE_LIMIT = 100
MAX_PAGES = 5


def map_telegram_error(exc: Exception) -> GiftApiError:
    if isinstance(exc, TelegramRetryAfter):
        return GiftApiError("rate_limited", f"Telegram ограничил частоту запросов. Повторите через {exc.retry_after} с.")
    if isinstance(exc, TelegramForbiddenError):
        return GiftApiError(
            "forbidden",
            "Недостаточно прав. Проверьте права бота: Настройки → Telegram Business → Чат-боты.",
        )
    if isinstance(exc, (TelegramNetworkError, TelegramServerError)):
        return GiftApiError("network", "Сетевая ошибка Telegram. Операция не выполнена, попробуйте позже.")
    if isinstance(exc, TelegramBadRequest):
        text = (exc.message or "").upper()
        if "BUSINESS" in text and ("INVALID" in text or "NOT FOUND" in text):
            return GiftApiError(
                "connection_invalid", "Подключение недействительно или истекло. Подключите бота заново."
            )
        if "RIGHT" in text:
            return GiftApiError("forbidden", "У бота нет права передавать подарки этого аккаунта.")
        if "BALANCE" in text or "NOT ENOUGH" in text or "STARS" in text:
            return GiftApiError("insufficient_stars", "Недостаточно Telegram Stars для комиссии за передачу.")
        if "PEER" in text or "USER" in text or "CHAT NOT FOUND" in text:
            return GiftApiError(
                "recipient_invalid",
                "Получатель недоступен. Telegram требует, чтобы получатель был активен в последние 24 часа.",
            )
        return GiftApiError("bad_request", f"Telegram отклонил операцию: {exc.message[:120]}")
    if isinstance(exc, TelegramAPIError):
        return GiftApiError("api_error", "Ошибка Telegram API. Операция не выполнена.")
    return GiftApiError("unknown", "Неизвестная ошибка. Операция не выполнена.")


def to_gift_info(owned: object) -> OwnedGiftInfo | None:
    if isinstance(owned, OwnedGiftUnique):
        if not owned.owned_gift_id:
            return None
        gift = owned.gift
        return OwnedGiftInfo(
            owned_gift_id=owned.owned_gift_id,
            title=f"{gift.base_name} #{gift.number}",
            is_unique=True,
            can_be_transferred=bool(owned.can_be_transferred),
            transfer_star_count=owned.transfer_star_count,
            next_transfer_date=owned.next_transfer_date,
            sticker_file_id=gift.model.sticker.file_id if gift.model and gift.model.sticker else None,
            unique_name=gift.name,
        )
    if isinstance(owned, OwnedGiftRegular):
        if not owned.owned_gift_id:
            return None
        return OwnedGiftInfo(
            owned_gift_id=owned.owned_gift_id,
            title=f"Подарок {owned.gift.star_count}⭐",
            is_unique=False,
            can_be_transferred=False,
            transfer_star_count=None,
            next_transfer_date=None,
            sticker_file_id=owned.gift.sticker.file_id if owned.gift.sticker else None,
        )
    return None


class TelegramGiftApi:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def list_owned_gifts(self, connection_id: str) -> list[OwnedGiftInfo]:
        result: list[OwnedGiftInfo] = []
        offset: str | None = None
        try:
            for _ in range(MAX_PAGES):
                page = await self._bot.get_business_account_gifts(
                    business_connection_id=connection_id, offset=offset, limit=PAGE_LIMIT
                )
                result.extend(info for g in page.gifts if (info := to_gift_info(g)) is not None)
                if not page.next_offset:
                    break
                offset = page.next_offset
        except Exception as exc:  # noqa: BLE001 - mapped to a user-facing error
            raise map_telegram_error(exc) from exc
        return result

    async def resolve_recipient(self, ref: RecipientRef) -> ResolvedRecipient:
        target: int | str = ref.user_id if ref.user_id is not None else f"@{ref.username}"
        try:
            chat = await self._bot.get_chat(target)
        except TelegramBadRequest as exc:
            if ref.user_id is not None:
                # Bots can only look up users they've seen; Telegram validates the ID on transfer.
                return ResolvedRecipient(chat_id=ref.user_id, label=ref.label, verified=False)
            raise GiftApiError(
                "recipient_not_found",
                "Пользователь не найден. Telegram позволяет боту найти только тех, кто ему писал — "
                "попросите получателя открыть бота или укажите числовой ID.",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise map_telegram_error(exc) from exc
        if chat.type != ChatType.PRIVATE:
            raise GiftApiError("recipient_not_user", "Получателем может быть только пользователь Telegram.")
        label = f"@{chat.username}" if chat.username else ref.label
        return ResolvedRecipient(chat_id=chat.id, label=label, verified=True)

    async def transfer(
        self, connection_id: str, owned_gift_id: str, new_owner_chat_id: int, star_count: int | None
    ) -> None:
        try:
            ok = await self._bot.transfer_gift(
                business_connection_id=connection_id,
                owned_gift_id=owned_gift_id,
                new_owner_chat_id=new_owner_chat_id,
                star_count=star_count or None,
            )
        except Exception as exc:  # noqa: BLE001
            raise map_telegram_error(exc) from exc
        if not ok:
            raise GiftApiError("api_error", "Telegram не подтвердил передачу.")
