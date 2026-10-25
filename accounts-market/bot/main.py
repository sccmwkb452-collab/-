"""Entry point: python -m bot.main"""

from __future__ import annotations

import asyncio
import logging
import secrets

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


def build_dispatcher(
    settings: Settings,
    sm,
    payments: PaymentService,
    bot_username: str,
    storage: BaseStorage,
    admin_ids: frozenset[int] | None = None,
) -> Dispatcher:
    admin_ids = settings.admin_ids if admin_ids is None else admin_ids
    dp = Dispatcher(storage=storage)
    dp.update.outer_middleware(ContextMiddleware(sm, admin_ids))
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp["payments"] = payments
    dp["bot_username"] = bot_username
    dp.include_router(errors.router)
    dp.include_router(build_router(admin_ids))
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
    token = settings.bot_token.get_secret_value()
    beta_only = not token and settings.beta_site
    if not token and not beta_only:
        raise SystemExit("BOT_TOKEN is not set")
    if not settings.admin_ids and not beta_only:
        log.warning("ADMIN_IDS is empty: the admin panel is unavailable")

    engine = create_engine(settings.database_url)
    sm = create_sessionmaker(engine)
    async with sm() as session:
        await shop_settings.ensure_defaults(session, settings.shop_name)
        await session.commit()

    bot: Bot | None = None
    username = "beta_preview_bot"
    if not beta_only:
        session = None
        if settings.telegram_api_url:
            from aiogram.client.session.aiohttp import AiohttpSession
            from aiogram.client.telegram import TelegramAPIServer

            session = AiohttpSession(api=TelegramAPIServer.from_base(settings.telegram_api_url))
        bot = Bot(token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
        username = (await bot.get_me()).username or ""

    provider = build_provider(settings, username)
    payments = PaymentService(
        sm, provider, ttl_minutes=settings.payment_ttl_minutes, max_amount=settings.max_topup_rub * 100
    )
    if provider.is_demo:
        log.warning("DEMO payment provider is active: no real money is processed")

    admin_ids = settings.admin_ids
    beta = None
    if settings.beta_site:
        from beta.site import ADMIN_ID as BETA_ADMIN_ID

        admin_ids = admin_ids | {BETA_ADMIN_ID}
    dp = build_dispatcher(settings, sm, payments, username, build_storage(settings), admin_ids)

    app = build_app(payments)
    if settings.beta_site:
        from beta.site import BetaSite

        key = settings.beta_key or secrets.token_urlsafe(18)
        beta = BetaSite(dp, token or "1:BETA", key)
        beta.routes(app)
        log.warning("BETA site: http://<host>:%s/beta/%s/", settings.webhook_port, key)

    real_notify = paid_notifier(bot) if bot else None
    beta_notify = paid_notifier(beta.bot) if beta else None

    async def on_paid(payment: Payment) -> None:
        if beta is not None and beta.owns(payment.user_id):
            await beta_notify(payment)
        elif real_notify is not None:
            await real_notify(payment)

    payments.on_paid = on_paid

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, settings.webhook_host, settings.webhook_port).start()
    poller = asyncio.create_task(poll_forever(payments, settings.payment_poll_seconds))
    try:
        if bot is None:
            log.info("running the beta site only (no BOT_TOKEN)")
            await asyncio.Event().wait()
        else:
            await bot.set_my_commands(COMMANDS)
            log.info("@%s started, provider=%s", username, provider.name)
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        poller.cancel()
        await runner.cleanup()
        await provider.close()
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
