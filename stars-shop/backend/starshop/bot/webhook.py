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
from typing import TYPE_CHECKING, Annotated, Any

import httpx
from fastapi import FastAPI, Header, Request

from ..config import get_settings
from ..shared.errors import Unauthorized
from .setup import ALLOWED_UPDATES, COMMANDS, MENU_BUTTON_TEXT

if TYPE_CHECKING:
    from aiogram import Bot

# aiogram is imported on first use: it takes seconds to import, and a cold
# start of the shop pages must not wait for the bot.

log = logging.getLogger("starshop.bot")
PATH = "/api/v1/webhooks/telegram"


def webhook_secret() -> str:
    s = get_settings()
    configured = s.bot_webhook_secret.get_secret_value()
    return configured or hmac.new(s.secret_key.get_secret_value().encode(), b"telegram-webhook", hashlib.sha256).hexdigest()


def webhook_url() -> str:
    return get_settings().public_base_url.rstrip("/") + PATH


def new_bot() -> Bot:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    # A new HTTP session per use: the instance can be frozen between requests.
    from .emoji import install

    return install(Bot(get_settings().bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML)))


async def telegram_update(request: Request, x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None) -> dict:
    if not hmac.compare_digest((x_telegram_bot_api_secret_token or "").encode(), webhook_secret().encode()):
        raise Unauthorized("Неверный секрет вебхука", code="webhook_secret_invalid")
    from aiogram.methods import TelegramMethod

    from .main import get_dispatcher

    update: dict[str, Any] = await request.json()
    async with new_bot() as bot:
        reply = await get_dispatcher().feed_webhook_update(bot, update)
        if isinstance(reply, TelegramMethod):
            await bot(reply)
    return {"ok": True}


def install(app: FastAPI) -> None:
    app.add_api_route(PATH, telegram_update, methods=["POST"], include_in_schema=False)


def _api_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10)


async def _call(client: httpx.AsyncClient, method: str, **params: Any) -> Any:
    s = get_settings()
    url = f"{s.telegram_api_base.rstrip('/')}/bot{s.bot_token.get_secret_value()}/{method}"
    try:
        data = (await client.post(url, json=params)).json()
    except (httpx.HTTPError, ValueError) as exc:
        # The request URL contains the token: only the method name is reported.
        raise RuntimeError(f"Telegram {method}: {type(exc).__name__}") from None
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data.get("result")


async def ensure_webhook() -> None:
    """Registers the webhook, the commands and the menu button when Telegram
    has something else. Plain Bot API calls: this runs after a response on a
    serverless instance, which must not spend seconds importing aiogram."""
    s = get_settings()
    url = webhook_url()
    menu = {"type": "web_app", "text": MENU_BUTTON_TEXT, "web_app": {"url": s.webapp_url}} if s.webapp_url.startswith("https://") else None
    async with _api_client() as client:
        info = await _call(client, "getWebhookInfo")
        hooked = info.get("url") == url and set(info.get("allowed_updates") or ()) == set(ALLOWED_UPDATES)
        current = await _call(client, "getChatMenuButton") if hooked and menu else None
        if hooked and (menu is None or (current or {}).get("text") == MENU_BUTTON_TEXT):
            commands = await _call(client, "getMyCommands")
            if [c.get("command") for c in commands or []] == [c for c, _ in COMMANDS]:
                return
        await _call(client, "setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS])
        if menu:
            await _call(client, "setChatMenuButton", menu_button=menu)
        if not hooked:
            # Last: a registered webhook marks the whole setup as done.
            await _call(
                client,
                "setWebhook",
                url=url,
                secret_token=webhook_secret(),
                allowed_updates=list(ALLOWED_UPDATES),
                drop_pending_updates=False,
            )
    log.info("bot setup refreshed", extra={"url": url, "webhook": not hooked})
