"""The bot inside the API on serverless hosting (Vercel), where no process
can keep polling Telegram.

Telegram sends updates to ``PUBLIC_BASE_URL`` + ``PATH`` with the secret
token header; ``ensure_webhook`` registers that URL (and the bot commands and
menu button) when it is not registered yet.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Annotated, Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.methods import TelegramMethod
from fastapi import FastAPI, Header, Request

from ..config import get_settings
from ..shared.errors import Unauthorized
from .main import configure_bot, get_dispatcher

log = logging.getLogger("starshop.bot")
PATH = "/api/v1/webhooks/telegram"


def webhook_secret() -> str:
    s = get_settings()
    configured = s.bot_webhook_secret.get_secret_value()
    return configured or hmac.new(s.secret_key.get_secret_value().encode(), b"telegram-webhook", hashlib.sha256).hexdigest()


def webhook_url() -> str:
    return get_settings().public_base_url.rstrip("/") + PATH


def new_bot() -> Bot:
    # A new HTTP session per use: the instance can be frozen between requests.
    return Bot(get_settings().bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def telegram_update(request: Request, x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None) -> dict:
    if not hmac.compare_digest((x_telegram_bot_api_secret_token or "").encode(), webhook_secret().encode()):
        raise Unauthorized("Неверный секрет вебхука", code="webhook_secret_invalid")
    update: dict[str, Any] = await request.json()
    async with new_bot() as bot:
        reply = await get_dispatcher().feed_webhook_update(bot, update)
        if isinstance(reply, TelegramMethod):
            await bot(reply)
    return {"ok": True}


def install(app: FastAPI) -> None:
    app.add_api_route(PATH, telegram_update, methods=["POST"], include_in_schema=False)


async def ensure_webhook() -> None:
    url = webhook_url()
    async with new_bot() as bot:
        info = await bot.get_webhook_info()
        if info.url == url:
            return
        await configure_bot(bot)  # first: the webhook marks the whole setup as done
        dp = get_dispatcher()
        await bot.set_webhook(
            url, secret_token=webhook_secret(), allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=False
        )
    log.info("bot webhook set", extra={"url": url})
