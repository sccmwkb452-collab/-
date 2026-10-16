from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.bot import texts
from nft_gift_bot.database.base import utcnow
from nft_gift_bot.handlers.common import respond
from nft_gift_bot.keyboards import inline
from nft_gift_bot.keyboards.main import MENU_CABINET, MENU_PAYMENTS, MENU_SETTINGS
from nft_gift_bot.models import ConnectionStatus, User
from nft_gift_bot.repositories import GiftRepository, GiftTransferRepository
from nft_gift_bot.services.crypto import SecretBox
from nft_gift_bot.services.payment_service import PaymentService
from nft_gift_bot.services.subscription_service import SubscriptionService
from nft_gift_bot.telegram_accounts.service import AccountConnectionService

router = Router(name="cabinet")


@router.message(F.text == MENU_CABINET)
async def cabinet(event: Message | CallbackQuery, session: AsyncSession, box: SecretBox, db_user: User, emoji: dict) -> None:
    account = await AccountConnectionService(session, box).get_latest(db_user.id)
    gifts_count = None
    if account and account.status == ConnectionStatus.ACTIVE:
        gifts_count = len(await GiftRepository(session).list_for_account(account.id))
    rich = texts.cabinet(
        emoji,
        db_user,
        await SubscriptionService(session).get(db_user.id),
        account,
        gifts_count,
        await GiftTransferRepository(session).count_succeeded_for_user(db_user.id),
        await PaymentService(session).list_for_user(db_user.id, 3),
        utcnow(),
    )
    await respond(event, rich, inline.connect(account))


@router.message(F.text == MENU_PAYMENTS)
async def payments(message: Message, session: AsyncSession, db_user: User, emoji: dict) -> None:
    await respond(message, texts.payments_list(emoji, await PaymentService(session).list_for_user(db_user.id, 10)))


@router.message(F.text == MENU_SETTINGS)
async def settings_screen(message: Message, session: AsyncSession, box: SecretBox, db_user: User, emoji: dict) -> None:
    account = await AccountConnectionService(session, box).get_active(db_user.id)
    sub = await SubscriptionService(session).get(db_user.id)
    await respond(message, texts.settings_screen(emoji, account, sub, utcnow()), inline.settings(account))
