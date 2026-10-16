"""Background jobs: payment confirmation polling and subscription expiry."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nft_gift_bot.bot import texts
from nft_gift_bot.bot.notifier import notify_admins, send_safe
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.database.base import utcnow
from nft_gift_bot.keyboards import inline
from nft_gift_bot.payments.ton import format_ton
from nft_gift_bot.payments.toncenter import ChainClient, ChainUnavailableError
from nft_gift_bot.repositories import UserRepository
from nft_gift_bot.services.payment_service import PaymentService
from nft_gift_bot.services.settings_service import SettingsService
from nft_gift_bot.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


async def check_payments_once(
    bot: Bot, factory: async_sessionmaker[AsyncSession], chain: ChainClient, settings: Settings
) -> int:
    if not settings.ton_receiver_address:
        return 0
    async with factory() as session:
        confirmed = await PaymentService(session).process_pending(chain, settings.ton_receiver_address, utcnow())
        await session.commit()
        emoji = await SettingsService(session, settings).emoji_overrides()
        for item in confirmed:
            user = await UserRepository(session).get(item.payment.user_id)
            sub = await SubscriptionService(session).get(item.payment.user_id)
            if user:
                await send_safe(bot, user.telegram_id, texts.payment_confirmed(emoji, sub), inline.after_payment())
            await notify_admins(
                bot, settings.admin_id_set,
                f"💳 Новый платёж: {format_ton(item.payment.amount_nano)} TON, счёт {item.payment.memo}",
            )
    return len(confirmed)


async def check_subscriptions_once(bot: Bot, factory: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    now = utcnow()
    async with factory() as session:
        service = SubscriptionService(session)
        expired = await service.expire_due(now)
        warned = await service.take_expiry_warnings(now, timedelta(hours=settings.expiry_warning_hours))
        await session.commit()
        emoji = await SettingsService(session, settings).emoji_overrides()
        users = UserRepository(session)
        for sub in expired:
            if user := await users.get(sub.user_id):
                await send_safe(bot, user.telegram_id, texts.subscription_expired(emoji), inline.subscription_offer())
        for sub in warned:
            if user := await users.get(sub.user_id):
                await send_safe(bot, user.telegram_id, texts.subscription_expiring(emoji, sub), inline.subscription_offer())


async def _loop(name: str, interval: float, job: Callable[[], Awaitable[object]], stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await job()
        except ChainUnavailableError as exc:
            logger.warning("job skipped: chain unavailable", extra={"job": name, "error": str(exc)})
        except Exception:  # noqa: BLE001 - a failing job must not kill the bot
            logger.exception("job failed", extra={"job": name})
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass


def start_background_jobs(
    bot: Bot, factory: async_sessionmaker[AsyncSession], chain: ChainClient, settings: Settings, stop: asyncio.Event
) -> list[asyncio.Task]:
    return [
        asyncio.create_task(
            _loop("payments", settings.payment_poll_seconds, lambda: check_payments_once(bot, factory, chain, settings), stop)
        ),
        asyncio.create_task(
            _loop("subscriptions", settings.subscription_check_seconds, lambda: check_subscriptions_once(bot, factory, settings), stop)
        ),
    ]
