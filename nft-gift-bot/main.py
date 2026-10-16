"""
Точка входа Telegram NFT Gift Bot.

Запуск:
    python main.py
"""

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from admin import admin_router
from bot.handlers import build_main_router
from bot.middlewares import DatabaseMiddleware, UserMiddleware
from config import settings
from database.session import create_all_tables, engine
from logging_setup import setup_logging
from services.scheduler import start_scheduler, stop_scheduler

# Ensure new models are registered in metadata for create_all_tables
import database.models.payment  # noqa: F401
import database.models.bot_setting  # noqa: F401

logger = logging.getLogger(__name__)
_scheduler_tasks: list = []


async def on_startup(bot: Bot) -> None:
    if not settings.is_production:
        # В dev-режиме создаём таблицы напрямую (без Alembic)
        await create_all_tables()
        logger.info("Database tables ensured (dev mode)")

    me = await bot.get_me()
    logger.info(
        "Bot started: @%s (id=%d) | env=%s",
        me.username,
        me.id,
        settings.app_env,
    )

    if settings.webhook_url:
        await bot.set_webhook(settings.webhook_url)
        logger.info("Webhook set: %s", settings.webhook_url)

    global _scheduler_tasks
    _scheduler_tasks = start_scheduler()


async def on_shutdown(bot: Bot) -> None:
    logger.info("Shutting down...")
    stop_scheduler(_scheduler_tasks)
    if settings.webhook_url:
        await bot.delete_webhook()
    await engine.dispose()
    logger.info("Engine disposed. Bye.")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # ── Middlewares ───────────────────────────────────────────────────────────
    # Порядок важен: сначала DB, затем User (зависит от session)
    dp.update.outer_middleware(DatabaseMiddleware())
    dp.update.outer_middleware(UserMiddleware())

    # ── Routers ───────────────────────────────────────────────────────────────
    dp.include_router(build_main_router())
    dp.include_router(admin_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return dp


async def main() -> None:
    setup_logging(
        log_level=settings.log_level,
        log_dir=Path("logs") if settings.is_production else None,
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    logger.info("Starting polling (no webhook configured)...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
