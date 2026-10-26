"""Telegram bot process (long polling).

Runs as its own service, independent of the web panel. A PostgreSQL advisory
lock held for the whole lifetime guarantees a single running instance: a
second process (or an accidental second deployment) exits immediately
instead of fighting over getUpdates.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from sqlalchemy import text

from ..config import get_settings
from ..database.session import dispose_engine, get_engine
from ..logging_setup import setup_logging
from ..services import health
from ..shared.timeutil import utcnow
from .core import AccessMiddleware
from .handlers import admin, autosettings, common, insights, listings, messages, orders, products, suppliers

log = logging.getLogger("autocommerce.bot")
LOCK_KEY = 0x504F4B42  # "POKB"

COMMANDS = [
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="start", description="Запуск и привязка аккаунта"),
    BotCommand(command="id", description="Мой Telegram ID"),
]


def storage() -> BaseStorage:
    url = get_settings().redis_url
    if url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(url)
    return MemoryStorage()


_dispatcher: Dispatcher | None = None


def build_dispatcher() -> Dispatcher:
    """The dispatcher is built once: routers are module-level and can be attached to one dispatcher only."""
    global _dispatcher
    if _dispatcher is not None:
        return _dispatcher
    dp = Dispatcher(storage=storage())
    middleware = AccessMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    # section routers first, the catch-all text handler of `common` last
    for module in (products, orders, messages, insights, suppliers, listings, autosettings, admin, common):
        dp.include_router(module.router)
    _dispatcher = dp
    return dp


def build_bot(token: str | None = None) -> Bot:
    return Bot(
        token or get_settings().bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


async def _heartbeat(stop: asyncio.Event, started) -> None:
    while not stop.is_set():
        try:
            await health.beat("bot", {"mode": "polling"}, started_at=started)
        except Exception:  # noqa: BLE001 - the database may be briefly unavailable
            log.warning("bot heartbeat failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            pass


async def main() -> int:
    setup_logging("bot")
    settings = get_settings()
    if not settings.bot_token.get_secret_value():
        log.error("BOT_TOKEN is not set")
        return 2
    engine = get_engine()
    lock_conn = await engine.connect()
    got = (await lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY})).scalar()
    if not got:
        log.error("another bot instance is already running (advisory lock is held) — exiting")
        await lock_conn.close()
        await dispose_engine()
        return 3
    bot = build_bot()
    dp = build_dispatcher()
    stop = asyncio.Event()
    started = utcnow()
    me = await bot.get_me()
    log.info("bot started", extra={"username": me.username})
    await bot.set_my_commands(COMMANDS)
    beat = asyncio.create_task(_heartbeat(stop, started))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(dp.stop_polling()))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), handle_signals=False)
    finally:
        stop.set()
        await beat
        await bot.session.close()
        await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
        await lock_conn.close()
        await dispose_engine()
        log.info("bot stopped")
    return 0


def run() -> None:
    sys.exit(asyncio.run(main()))
