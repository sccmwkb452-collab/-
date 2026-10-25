"""Entry point: python -m bot.main"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from aiohttp import web

from bot import errors
from bot.config import Settings, get_settings
from bot.middlewares import ContextMiddleware
from database.models import Payment
from database.session import create_engine, create_sessionmaker
from handlers import build_router
from keyboards.user import btn, rows
from payments.registry import build_provider
from payments.service import PaymentService
from payments.webhooks import build_app, poll_forever
from services import shop_settings
from services.formatting import money

log = logging.getLogger("bot")


def build_storage(settings: Settings) -> BaseStorage:
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(settings.redis_url)
    return MemoryStorage()


def build_dispatcher(settings: Settings, sm, payments: PaymentService, bot_username: str, storage: BaseStorage) -> Dispatcher:
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(ContextMiddleware(sm, settings.admin_ids))
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp["payments"] = payments
    dp["bot_username"] = bot_username
    dp.include_router(errors.router)
    dp.include_router(build_router(settings.admin_ids))
    return dp


def paid_notifier(bot: Bot):
    from bot.callbacks import Nav

    async def notify(payment: Payment) -> None:
        try:
            await bot.send_message(
                payment.user_id,
                f"✅ <b>Оплата получена</b>\n\nБаланс пополнен на <b>{money(payment.amount)}</b>.",
                reply_markup=rows([btn("🛍 Перейти в каталог", Nav(to="catalog"), style="primary")], [btn("👤 Кабинет", Nav(to="profile"))]),
            )
        except TelegramAPIError:
            log.info("could not notify user about payment %s", payment.id)

    return notify


COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="profile", description="Личный кабинет"),
    BotCommand(command="topup", description="Пополнить баланс"),
    BotCommand(command="support", description="Поддержка"),
]


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    if not settings.bot_token.get_secret_value():
        raise SystemExit("BOT_TOKEN is not set")
    if not settings.admin_ids:
        log.warning("ADMIN_IDS is empty: the admin panel is unavailable")

    engine = create_engine(settings.database_url)
    sm = create_sessionmaker(engine)
    async with sm() as session:
        await shop_settings.ensure_defaults(session, settings.shop_name)
        await session.commit()

    session = None
    if settings.telegram_api_url:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer

        session = AiohttpSession(api=TelegramAPIServer.from_base(settings.telegram_api_url))
    bot = Bot(
        settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    me = await bot.get_me()
    provider = build_provider(settings, me.username or "")
    payments = PaymentService(
        sm, provider, ttl_minutes=settings.payment_ttl_minutes, max_amount=settings.max_topup_rub * 100
    )
    payments.on_paid = paid_notifier(bot)
    if provider.is_demo:
        log.warning("DEMO payment provider is active: no real money is processed")

    dp = build_dispatcher(settings, sm, payments, me.username or "", build_storage(settings))

    runner = web.AppRunner(build_app(payments))
    await runner.setup()
    await web.TCPSite(runner, settings.webhook_host, settings.webhook_port).start()
    poller = asyncio.create_task(poll_forever(payments, settings.payment_poll_seconds))

    await bot.set_my_commands(COMMANDS)
    log.info("@%s started, provider=%s", me.username, provider.name)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        poller.cancel()
        await runner.cleanup()
        await provider.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
