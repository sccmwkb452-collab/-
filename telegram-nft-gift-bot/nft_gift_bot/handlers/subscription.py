from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.bot import texts
from nft_gift_bot.bot.notifier import notify_admins
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.database.base import utcnow
from nft_gift_bot.handlers.common import respond
from nft_gift_bot.keyboards import inline
from nft_gift_bot.keyboards.callbacks import SubCb
from nft_gift_bot.keyboards.main import MENU_SUBSCRIPTION
from nft_gift_bot.models import PaymentStatus, User
from nft_gift_bot.payments.ton import format_ton, ton_transfer_link, tonkeeper_link
from nft_gift_bot.payments.toncenter import ChainClient, ChainUnavailableError
from nft_gift_bot.repositories import PaymentRepository
from nft_gift_bot.services.payment_service import PaymentService
from nft_gift_bot.services.settings_service import SettingsService
from nft_gift_bot.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = Router(name="subscription")


@router.message(F.text == MENU_SUBSCRIPTION)
@router.callback_query(SubCb.filter(F.action == "offer"))
async def offer(event: Message | CallbackQuery, session: AsyncSession, settings: Settings, db_user: User, emoji: dict) -> None:
    cfg = SettingsService(session, settings)
    sub = await SubscriptionService(session).get(db_user.id)
    rich = texts.subscription_offer(emoji, await cfg.subscription_price_ton(), await cfg.subscription_days(), sub, utcnow())
    await respond(event, rich, inline.subscription_offer())


@router.callback_query(SubCb.filter(F.action == "buy"))
async def buy(cb: CallbackQuery, session: AsyncSession, settings: Settings, db_user: User, emoji: dict) -> None:
    if not settings.ton_receiver_address:
        await respond(cb, texts.error(emoji, "Приём платежей ещё не настроен. Обратитесь в поддержку."))
        return
    cfg = SettingsService(session, settings)
    payment = await PaymentService(session).create_subscription_invoice(
        db_user.id,
        await cfg.subscription_price_nano(),
        await cfg.subscription_days(),
        timedelta(minutes=settings.payment_ttl_minutes),
        utcnow(),
    )
    address = settings.ton_receiver_address
    await respond(
        cb,
        texts.invoice(emoji, payment, address, ton_transfer_link(address, payment.amount_nano, payment.memo)),
        inline.invoice(payment.id, tonkeeper_link(address, payment.amount_nano, payment.memo)),
    )


@router.callback_query(SubCb.filter(F.action == "check"))
async def check(
    cb: CallbackQuery,
    callback_data: SubCb,
    session: AsyncSession,
    settings: Settings,
    db_user: User,
    chain: ChainClient,
    emoji: dict,
) -> None:
    payment = await PaymentRepository(session).get_for_user(callback_data.payment_id, db_user.id)
    if payment is None:
        await cb.answer("Счёт не найден.", show_alert=True)
        return
    if payment.status == PaymentStatus.PAID:
        await cb.answer("Этот счёт уже оплачен.", show_alert=True)
        return
    if payment.status != PaymentStatus.PENDING:
        await cb.answer(f"Статус счёта: {texts.PAYMENT_STATUS.get(payment.status, payment.status)}", show_alert=True)
        return
    try:
        confirmed = await PaymentService(session).process_pending(
            chain, settings.ton_receiver_address, utcnow(), only_payment_id=payment.id
        )
    except ChainUnavailableError:
        logger.warning("chain unavailable on manual check")
        await cb.answer("Сеть TON сейчас недоступна. Бот проверит платёж автоматически.", show_alert=True)
        return
    if not confirmed:
        await cb.answer(
            f"Платёж пока не найден. Бот проверяет блокчейн каждые {settings.payment_poll_seconds} с.",
            show_alert=True,
        )
        return
    sub = await SubscriptionService(session).get(db_user.id)
    await respond(cb, texts.payment_confirmed(emoji, sub), inline.after_payment())
    await notify_admins(
        cb.bot, settings.admin_id_set,
        f"💳 Новый платёж: {format_ton(payment.amount_nano)} TON, счёт {payment.memo}, пользователь {db_user.telegram_id}",
    )


@router.callback_query(SubCb.filter(F.action == "cancel"))
async def cancel(cb: CallbackQuery, callback_data: SubCb, session: AsyncSession, db_user: User, emoji: dict) -> None:
    if await PaymentService(session).cancel(callback_data.payment_id, db_user.id):
        await respond(cb, texts.notice(emoji, "payment", "Счёт отменён"), edit=True)
    else:
        await cb.answer("Этот счёт уже нельзя отменить.", show_alert=True)
