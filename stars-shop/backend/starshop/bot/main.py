"""Telegram bot entry point: ``python -m starshop.bot``.

Polling by default; set BOT_MODE=webhook to receive updates through nginx
at PUBLIC_BASE_URL + BOT_WEBHOOK_PATH (protected by a secret token).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from ..config import get_settings
from ..database.session import dispose_engine
from ..logging_setup import setup_logging
from .handlers import admin, menu, support
from .keyboards import can_use_webapp
from .middlewares import DbMiddleware

log = logging.getLogger("starshop.bot")


def build_storage() -> BaseStorage:
    url = get_settings().redis_url
    if url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(url)
    return MemoryStorage()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=build_storage())
    middleware = DbMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    # support first: its state handlers must win over generic ones
    dp.include_routers(support.router, admin.router, menu.router)
    return dp


_dispatcher: Dispatcher | None = None


def get_dispatcher() -> Dispatcher:
    """The dispatcher of this process: routers are module singletons and can
    be attached to one dispatcher only."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = build_dispatcher()
    return _dispatcher


async def configure_bot(bot: Bot) -> None:
    s = get_settings()
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="orders", description="Мои заказы"),
            BotCommand(command="profile", description="Мой профиль"),
            BotCommand(command="support", description="Поддержка"),
        ]
    )
    if can_use_webapp():
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=s.webapp_url)))


async def run() -> None:
    setup_logging("bot")
    s = get_settings()
    token = s.bot_token.get_secret_value()
    if not token:
        raise SystemExit("BOT_TOKEN is not set")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = get_dispatcher()
    try:
        await configure_bot(bot)
    except Exception:
        log.exception("could not configure bot commands/menu")
    try:
        if s.bot_mode == "webhook":
            await _run_webhook(bot, dp)
        else:
            await bot.delete_webhook(drop_pending_updates=False)
            log.info("bot polling started")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await dispose_engine()


async def _run_webhook(bot: Bot, dp: Dispatcher) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    s = get_settings()
    secret = s.bot_webhook_secret.get_secret_value()
    if not secret:
        raise SystemExit("BOT_WEBHOOK_SECRET is required in webhook mode")
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=s.bot_webhook_path)
    app.router.add_get("/healthz", lambda request: web.json_response({"status": "ok"}))
    setup_application(app, dp, bot=bot)
    url = s.public_base_url.rstrip("/") + s.bot_webhook_path
    await bot.set_webhook(url, secret_token=secret, allowed_updates=dp.resolve_used_update_types(), drop_pending_updates=False)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", s.bot_webhook_port).start()
    log.info("bot webhook started", extra={"path": s.bot_webhook_path})
    await asyncio.Event().wait()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
