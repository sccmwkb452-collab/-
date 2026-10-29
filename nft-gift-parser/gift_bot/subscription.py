"""Обязательная подписка: middleware не пускает дальше, пока пользователь не подписан."""
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from gift_bot.common import LINE, PRIMARY, SUCCESS, btn, main_menu, main_text
from gift_bot.config import Config
from gift_bot.db import Channel, Database

logger = logging.getLogger(__name__)

router = Router(name="subscription")

CHECK_CB = "sub:check"
CACHE_TTL = 60
NOT_MEMBER = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}

_ok_until: dict[int, float] = {}


async def missing_channels(bot: Bot, db: Database, user_id: int) -> list[Channel]:
    missing = []
    for ch in db.channels():
        try:
            member = await bot.get_chat_member(ch.chat_id, user_id)
        except TelegramAPIError as exc:
            # Бота убрали из канала — не блокируем пользователей из-за ошибки настройки.
            logger.warning("Не могу проверить подписку на %s: %s", ch.chat_id, exc)
            continue
        if member.status in NOT_MEMBER or (
            member.status == ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", True)
        ):
            missing.append(ch)
    return missing


def subscribe_kb(channels: list[Channel]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📢 {ch.title}", url=ch.url, style=PRIMARY)] for ch in channels]
    rows.append([btn("✅ Я подписался", CHECK_CB, SUCCESS)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


SUBSCRIBE_TEXT = (
    f"🔒 <b>Д О С Т У П   З А К Р Ы Т</b>\n{LINE}\n"
    "<blockquote>Подпишись на каналы ниже и нажми «✅ Я подписался» — бот сразу откроется.</blockquote>"
)


class SubscriptionMiddleware(BaseMiddleware):
    """Регистрирует пользователя и проверяет подписку перед каждым апдейтом."""

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        db: Database = data["db"]
        config: Config = data["config"]
        if user is None:
            return await handler(event, data)
        if isinstance(event, Message) and event.chat.type != "private":
            return None
        db.touch_user(user.id, user.username, user.first_name)

        if user.id in config.admin_ids or (isinstance(event, CallbackQuery) and event.data == CHECK_CB):
            return await handler(event, data)
        if _ok_until.get(user.id, 0) > time.monotonic():
            return await handler(event, data)

        missing = await missing_channels(data["bot"], db, user.id)
        if not missing:
            _ok_until[user.id] = time.monotonic() + CACHE_TTL
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("Сначала подпишись на каналы", show_alert=True)
            await event.message.answer(SUBSCRIBE_TEXT, reply_markup=subscribe_kb(missing))
        else:
            await event.answer(SUBSCRIBE_TEXT, reply_markup=subscribe_kb(missing))
        return None


@router.callback_query(F.data == CHECK_CB)
async def check(c: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    missing = await missing_channels(bot, db, c.from_user.id)
    if missing:
        await c.answer("❌ Ты подписался не на все каналы", show_alert=True)
        try:
            await c.message.edit_reply_markup(reply_markup=subscribe_kb(missing))
        except TelegramBadRequest:  # кнопки не изменились
            pass
        return
    _ok_until[c.from_user.id] = time.monotonic() + CACHE_TTL
    await c.answer("✅ Спасибо за подписку!")
    await c.message.edit_text(main_text(db.count_gifts(), len(db.collections())),
                              reply_markup=main_menu(c.from_user.id in config.admin_ids))
