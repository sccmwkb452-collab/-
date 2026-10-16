"""Клиент для работы с Telegram Gift API через aiogram."""
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


@dataclass
class TelegramGift:
    gift_id: str
    sticker_file_id: str
    star_count: int       # Стоимость в Stars
    total_count: int | None = None
    remaining_count: int | None = None


class GiftManagerClient:
    """Обёртка над Telegram Bot API для операций с подарками."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def get_available_gifts(self) -> list[TelegramGift]:
        """
        Получает список подарков, доступных для отправки.
        Telegram API: getAvailableGifts
        """
        try:
            # aiogram 3.x: await self._bot.get_available_gifts()
            # Возвращает объект Gifts со списком Gift-объектов
            result = await self._bot.get_available_gifts()
            return [
                TelegramGift(
                    gift_id=g.id,
                    sticker_file_id=g.sticker.file_id,
                    star_count=g.star_count,
                    total_count=g.total_count,
                    remaining_count=g.remaining_count,
                )
                for g in result.gifts
            ]
        except TelegramAPIError as e:
            logger.error("Failed to get available gifts: %s", e)
            return []

    async def send_gift(
        self,
        user_id: int,
        gift_id: str,
        text: str | None = None,
    ) -> bool:
        """
        Отправляет подарок пользователю.
        Telegram API: sendGift
        """
        try:
            await self._bot.send_gift(
                user_id=user_id,
                gift_id=gift_id,
                text=text,
            )
            logger.info("Gift %r sent to user %d", gift_id, user_id)
            return True
        except TelegramAPIError as e:
            logger.error("Failed to send gift %r to user %d: %s", gift_id, user_id, e)
            return False

    async def transfer_gift(
        self,
        business_connection_id: str,
        gift_id: str,
        new_owner_chat_id: int,
        star_count: int,
    ) -> bool:
        """
        Передаёт NFT-подарок другому пользователю.
        Telegram API: transferGift (Bot API 9.0+)
        Требует бизнес-аккаунт и подключение через Business Bot API.
        """
        try:
            await self._bot.transfer_gift(
                business_connection_id=business_connection_id,
                owned_gift_id=gift_id,
                new_owner_chat_id=new_owner_chat_id,
                star_count=star_count,
            )
            logger.info(
                "Gift %r transferred to user %d (cost %d stars)",
                gift_id,
                new_owner_chat_id,
                star_count,
            )
            return True
        except TelegramAPIError as e:
            logger.error("Failed to transfer gift %r: %s", gift_id, e)
            return False
