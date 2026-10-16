from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nft_gift_bot.config.settings import Settings
from nft_gift_bot.gifts.api import GiftApi
from nft_gift_bot.handlers import account, cabinet, gifts, start, subscription, support
from nft_gift_bot.handlers.admin import create_admin_router
from nft_gift_bot.middlewares.context import DbSessionMiddleware, EmojiMiddleware, UserContextMiddleware
from nft_gift_bot.payments.toncenter import ChainClient
from nft_gift_bot.services.crypto import SecretBox
from nft_gift_bot.services.rate_limit import SlidingWindowRateLimiter


def build_dispatcher(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    box: SecretBox,
    chain: ChainClient,
    gift_api: GiftApi,
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), settings=settings, box=box, chain=chain, gift_api=gift_api)

    dp.update.outer_middleware(DbSessionMiddleware(session_factory))
    dp.update.outer_middleware(EmojiMiddleware(settings))
    user_ctx = UserContextMiddleware(SlidingWindowRateLimiter(settings.rate_limit_per_minute))
    dp.message.outer_middleware(user_ctx)
    dp.callback_query.outer_middleware(user_ctx)

    dp.include_routers(
        create_admin_router(settings.admin_id_set),
        start.router,
        subscription.router,
        account.router,
        cabinet.router,
        support.router,
        gifts.router,
        gifts.intent_router,  # must stay last: catches any remaining text
    )
    return dp
