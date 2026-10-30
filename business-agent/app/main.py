"""Точка входа: python -m app.main"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.ai.llm import build_llm
from app.bot.handlers import build_routers
from app.bot.middlewares import DedupMiddleware
from app.bot.session import EnvAwareSession
from app.business.service import BusinessService
from app.config import get_settings
from app.context import AppContext
from app.core.logging_setup import setup_logging
from app.db.session import create_schema, dispose_engine, init_engine
from app.deals.manager import DealManager
from app.media.analyzer import MediaAnalyzer, telegram_downloader
from app.nft.pages import GiftPageClient
from app.outreach.service import OutreachService
from app.scheduler import Scheduler
from app.trading.registry import AdapterFactory

logger = logging.getLogger("app")


def build_storage(redis_url: str):
    if not redis_url:
        return MemoryStorage()
    from aiogram.fsm.storage.redis import RedisStorage

    return RedisStorage.from_url(redis_url)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    if not settings.bot_token:
        logger.critical("BOT_TOKEN не задан — заполните .env (см. .env.example)")
        sys.exit(1)

    sessions = init_engine(settings.database_url)
    await create_schema()

    bot = Bot(settings.bot_token, session=EnvAwareSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    llm = build_llm(settings)
    if llm is None:
        logger.warning("ANTHROPIC_API_KEY не задан: агент не будет отвечать, анализ медиа отключён")
    factory = AdapterFactory(settings)
    ctx = AppContext(
        settings=settings, bot=bot, sessions=sessions, llm=llm,
        media=MediaAnalyzer(llm, telegram_downloader(bot), ffmpeg=settings.ffmpeg_path,
                            max_frames=settings.media_max_frames, max_bytes=settings.media_max_download_bytes),
        trade_adapters=factory, deals=DealManager(factory), gifts=GiftPageClient(),
    )
    ctx.business = BusinessService(ctx)
    ctx.outreach = OutreachService(ctx, ctx.business)

    dp = Dispatcher(storage=build_storage(settings.redis_url))
    dp.update.outer_middleware(DedupMiddleware(ctx))
    dp.include_routers(*build_routers(ctx))

    scheduler = Scheduler(ctx, ctx.business, ctx.outreach)
    try:
        me = await bot.me()
        logger.info("Запущен @%s", me.username)
        if not me.can_connect_to_business:
            logger.warning("У бота выключен Business Mode — включите в @BotFather → Bot Settings → Business Mode")
        await bot.set_my_commands([BotCommand(command="start", description="Панель управления"),
                                   BotCommand(command="menu", description="Главное меню")])
        scheduler.start()
        # drop_pending_updates=False: сообщения, пришедшие во время простоя, тоже обрабатываются;
        # повторная доставка отсекается DedupMiddleware.
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await scheduler.stop()
        await factory.close()
        await ctx.gifts.close()
        await bot.session.close()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
