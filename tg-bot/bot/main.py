import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database.session import create_tables
from bot.handlers import setup_routers
from bot.logging_config import setup_logging
from bot.middlewares import DatabaseMiddleware, UserMiddleware

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    await create_tables()
    me = await bot.get_me()
    logger.info("Bot started: @%s (%d)", me.username, me.id)


async def on_shutdown(bot: Bot) -> None:
    logger.info("Bot shutting down...")


async def main() -> None:
    setup_logging()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Middlewares (order matters: db first, then user)
    dp.update.outer_middleware(DatabaseMiddleware())
    dp.update.outer_middleware(UserMiddleware())

    dp.include_router(setup_routers())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
