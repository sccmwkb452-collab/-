from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from nft_gift_bot.bot.factory import build_dispatcher
from nft_gift_bot.bot.scheduler import start_background_jobs
from nft_gift_bot.config.logging import setup_logging
from nft_gift_bot.config.settings import get_settings
from nft_gift_bot.database.session import create_engine, create_session_factory
from nft_gift_bot.gifts.telegram_api import TelegramGiftApi
from nft_gift_bot.payments.toncenter import TonCenterClient
from nft_gift_bot.services.crypto import SecretBox

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    setup_logging(
        settings.log_level,
        [settings.bot_token.get_secret_value(), settings.encryption_key.get_secret_value(), settings.ton_api_key.get_secret_value()],
    )
    settings.validate_runtime()
    if not settings.admin_id_set:
        logger.warning("ADMIN_IDS is empty: admin panel is disabled")

    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    box = SecretBox(settings.encryption_key.get_secret_value())
    chain = TonCenterClient(settings.ton_api_url, settings.ton_api_key.get_secret_value())
    bot = Bot(settings.bot_token.get_secret_value(), default=DefaultBotProperties(link_preview_is_disabled=True))
    dp = build_dispatcher(settings, factory, box, chain, TelegramGiftApi(bot))

    stop = asyncio.Event()
    tasks = start_background_jobs(bot, factory, chain, settings, stop)
    logger.info("bot starting", extra={"environment": settings.environment})
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await chain.close()
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())
