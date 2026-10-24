"""Telegram Premium (custom) emoji in the bot.

IDs are set in Admin → Настройки → Эмодзи бота. Telegram shows custom emoji
from a bot only when its owner has Telegram Premium (or the bot has a
collectible username from Fragment). If Telegram refuses a message because of
them, the request middleware sends it again with the usual emoji, so a wrong
ID or an expired subscription never breaks the bot.
"""

from __future__ import annotations

import logging
import re
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import TelegramMethod
from aiogram.methods.base import Response, TelegramType
from aiogram.types import InlineKeyboardMarkup

from ..services.app_settings import RuntimeSettings

log = logging.getLogger(__name__)
TG_EMOJI = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.S)
# The usual emoji shown instead of each custom one.
FALLBACK = {
    "welcome": "✨",
    "shop": "🌐",
    "stars": "⭐️",
    "premium": "💎",
    "profile": "👤",
    "orders": "🧾",
    "referrals": "🎁",
    "support": "💬",
    "lucky": "🍀",
    "success": "✅",
}


def emoji_id(runtime: RuntimeSettings | None, key: str) -> str | None:
    if runtime is None or not runtime.bot_emoji.enabled:
        return None
    return runtime.bot_emoji.ids.get(key)


def em(runtime: RuntimeSettings | None, key: str) -> str:
    """For message text (HTML): the custom emoji with the usual one as its fallback."""
    fallback = FALLBACK[key]
    eid = emoji_id(runtime, key)
    return f'<tg-emoji emoji-id="{escape(eid)}">{fallback}</tg-emoji>' if eid else fallback


def has_custom(method: TelegramMethod[Any]) -> bool:
    for field in ("text", "caption"):
        value = getattr(method, field, None)
        if isinstance(value, str) and "<tg-emoji" in value:
            return True
    markup = getattr(method, "reply_markup", None)
    if isinstance(markup, InlineKeyboardMarkup):
        return any(b.icon_custom_emoji_id for row in markup.inline_keyboard for b in row)
    return False


def strip_custom(method: TelegramMethod[Any]) -> TelegramMethod[Any]:
    """The same request with the usual emoji: tags unwrapped, icons replaced by their emoji."""
    updates: dict[str, Any] = {}
    for field in ("text", "caption"):
        value = getattr(method, field, None)
        if isinstance(value, str):
            updates[field] = TG_EMOJI.sub(r"\1", value)
    markup = getattr(method, "reply_markup", None)
    if isinstance(markup, InlineKeyboardMarkup):
        rows = []
        for row in markup.inline_keyboard:
            new_row = []
            for b in row:
                if b.icon_custom_emoji_id:
                    prefix = ICON_FALLBACK.get(b.icon_custom_emoji_id, "")
                    b = b.model_copy(update={"icon_custom_emoji_id": None, "text": f"{prefix} {b.text}".strip()})
                new_row.append(b)
            rows.append(new_row)
        updates["reply_markup"] = InlineKeyboardMarkup(inline_keyboard=rows)
    return method.model_copy(update=updates)


# icon id → the usual emoji, filled while keyboards are built.
ICON_FALLBACK: dict[str, str] = {}


class CustomEmojiFallback(BaseRequestMiddleware):
    async def __call__(
        self, make_request: NextRequestMiddlewareType[TelegramType], bot: Bot, method: TelegramMethod[TelegramType]
    ) -> Response[TelegramType]:
        if not has_custom(method):
            return await make_request(bot, method)
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as exc:
            log.warning("custom emoji refused, sent with the usual ones", extra={"method": method.__api_method__, "error": str(exc)[:200]})
            return await make_request(bot, strip_custom(method))


def install(bot: Bot) -> Bot:
    bot.session.middleware(CustomEmojiFallback())
    return bot
