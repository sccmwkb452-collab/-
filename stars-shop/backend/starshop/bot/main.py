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
from aiogram.types import BotCommand, ErrorEvent, MenuButtonWebApp, WebAppInfo

from ..config import get_settings
from ..database.session import dispose_engine
from ..logging_setup import setup_logging
from ..services import errors
from .handlers import admin, buy, menu, payments, support
from .keyboards import can_use_webapp
from .middlewares import DbMiddleware
from .storage import DbStorage

log = logging.getLogger("starshop.bot")


def build_storage() -> BaseStorage:
    url = get_settings().redis_url
    if url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(url)
    # PostgreSQL keeps dialogues across instances and restarts.
    return DbStorage()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=build_storage())
    middleware = DbMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    dp.pre_checkout_query.outer_middleware(middleware)
    # support and buy first: their state handlers must win over generic ones;
    # menu last: it has the catch-all handler
    dp.include_routers(support.router, admin.router, buy.router, payments.router, menu.router)
    dp.errors.register(on_error)
    return dp


async def on_error(event: ErrorEvent) -> bool:
    """Logs the failure, tells the user and answers Telegram with 200 (a
    failing update is not re-delivered over and over)."""
    log.exception("bot update failed", exc_info=event.exception)
    await errors.record("bot", f"{event.exception.__class__.__name__}: {event.exception}")
    update = event.update
    target = update.message or (update.callback_query.message if update.callback_query else None)
    try:
        if update.callback_query is not None:
            await update.callback_query.answer("Что-то пошло не так. Попробуйте ещё раз", show_alert=True)
        elif target is not None:
            await target.answer("😔 Что-то пошло не так. Попробуйте ещё раз или напишите в поддержку.")
    except Exception:  # noqa: BLE001 - nothing more to do
        pass
    return True


_dispatcher: Dispatcher | None = None


def get_dispatcher() -> Dispatcher:
    """The dispatcher of this process: routers are module singletons and can
    be attached to one dispatcher only."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = build_dispatcher()
    return _dispatcher


MENU_BUTTON_TEXT = "🌐 Открыть магазин"


async def configure_bot(bot: Bot) -> None:
    s = get_settings()
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="buy", description="Купить Stars"),
            BotCommand(command="orders", description="Мои заказы"),
            BotCommand(command="profile", description="Мой профиль"),
            BotCommand(command="ref", description="Реферальная программа"),
            BotCommand(command="support", description="Поддержка"),
        ]
    )
    if can_use_webapp():
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text=MENU_BUTTON_TEXT, web_app=WebAppInfo(url=s.webapp_url)))


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
