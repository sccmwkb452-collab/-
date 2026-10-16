"""Business connection updates and the "connect account" screens."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import BusinessConnection, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.bot import texts
from nft_gift_bot.bot.notifier import send_safe
from nft_gift_bot.database.base import utcnow
from nft_gift_bot.handlers.common import respond
from nft_gift_bot.keyboards import inline
from nft_gift_bot.keyboards.callbacks import AccountCb
from nft_gift_bot.keyboards.main import MENU_CONNECT
from nft_gift_bot.models import User
from nft_gift_bot.services.crypto import SecretBox
from nft_gift_bot.services.settings_service import SettingsService
from nft_gift_bot.services.subscription_service import SubscriptionService
from nft_gift_bot.telegram_accounts.service import (
    AccountConnectionService,
    BusinessConnectionEvent,
    ConnectionOutcome,
)

logger = logging.getLogger(__name__)
router = Router(name="account")


@router.business_connection()
async def on_business_connection(
    connection: BusinessConnection, bot: Bot, session: AsyncSession, box: SecretBox, settings, emoji: dict
) -> None:
    rights = connection.rights
    event = BusinessConnectionEvent(
        connection_id=connection.id,
        owner_telegram_id=connection.user.id,
        is_enabled=connection.is_enabled,
        can_view_gifts=bool(rights and rights.can_view_gifts_and_stars),
        can_transfer_gifts=bool(rights and rights.can_transfer_and_upgrade_gifts),
        can_transfer_stars=bool(rights and rights.can_transfer_stars),
    )
    result = await AccountConnectionService(session, box).handle_event(event, utcnow())
    logger.info("business connection", extra={"outcome": result.outcome, "owner_id": connection.user.id})
    chat_id = connection.user_chat_id
    if result.outcome is ConnectionOutcome.CONNECTED and result.account:
        await send_safe(bot, chat_id, texts.connected(emoji, result.account), inline.connect(result.account))
    elif result.outcome is ConnectionOutcome.UPDATED and result.account:
        await send_safe(bot, chat_id, texts.notice(emoji, "security", "Права подключения обновлены"), inline.connect(result.account))
    elif result.outcome is ConnectionOutcome.NO_SUBSCRIPTION:
        price = await SettingsService(session, settings).subscription_price_ton()
        await send_safe(
            bot, chat_id,
            texts.notice(emoji, "warning", "Подключение не активировано",
                         f"Нужна активная подписка ({price.normalize():f} TON). Оформите её и подключите бота заново."),
            inline.subscription_offer(),
        )
    elif result.outcome is ConnectionOutcome.UNKNOWN_USER:
        await send_safe(
            bot, chat_id,
            texts.notice(emoji, "warning", "Сначала откройте бота", "Отправьте /start, оформите подписку и подключите бота заново."),
        )
    elif result.outcome is ConnectionOutcome.DISABLED:
        await send_safe(bot, chat_id, texts.notice(emoji, "security", "Подключение выключено", "Операции с аккаунтом остановлены."))


@router.message(F.text == MENU_CONNECT)
@router.callback_query(AccountCb.filter(F.action == "status"))
async def status(event: Message | CallbackQuery, bot: Bot, session: AsyncSession, box: SecretBox, db_user: User, emoji: dict) -> None:
    service = AccountConnectionService(session, box)
    account = await service.get_latest(db_user.id)
    has_sub = await SubscriptionService(session).is_active(db_user.id, utcnow())
    me = await bot.me()
    await respond(event, texts.connect_screen(emoji, account, has_sub, me.username or "bot"), inline.connect(account))


@router.callback_query(AccountCb.filter(F.action == "revoke"))
async def revoke_ask(cb: CallbackQuery, emoji: dict) -> None:
    await respond(cb, texts.revoke_confirm(emoji), inline.revoke_confirm())


@router.callback_query(AccountCb.filter(F.action == "revoke_yes"))
async def revoke(cb: CallbackQuery, session: AsyncSession, box: SecretBox, db_user: User, emoji: dict) -> None:
    if await AccountConnectionService(session, box).revoke(db_user.id, utcnow()):
        await respond(cb, texts.revoked(emoji), edit=True)
    else:
        await cb.answer("Активного подключения нет.", show_alert=True)


@router.callback_query(AccountCb.filter(F.action.in_({"notify_on", "notify_off"})))
async def toggle_notify(cb: CallbackQuery, callback_data: AccountCb, session: AsyncSession, box: SecretBox, db_user: User) -> None:
    enabled = callback_data.action == "notify_on"
    if await AccountConnectionService(session, box).set_notify(db_user.id, enabled):
        await cb.answer("Уведомления включены." if enabled else "Уведомления выключены.")
    else:
        await cb.answer("Аккаунт не подключён.", show_alert=True)
