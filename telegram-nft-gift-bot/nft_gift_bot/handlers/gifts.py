"""Gift list, gift card, owner-confirmed transfer flow and operation history."""

from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.bot import texts
from nft_gift_bot.bot.notifier import notify_admins
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.database.base import utcnow
from nft_gift_bot.gifts.api import GiftApi, GiftApiError
from nft_gift_bot.gifts.intent import parse_transfer_intent
from nft_gift_bot.gifts.recipient import RecipientRef, parse_recipient
from nft_gift_bot.gifts.service import GiftAccessError, GiftService
from nft_gift_bot.handlers.common import respond
from nft_gift_bot.keyboards import inline
from nft_gift_bot.keyboards.callbacks import GiftCb
from nft_gift_bot.keyboards.main import MENU_GIFTS, MENU_HISTORY, MENU_ITEMS
from nft_gift_bot.models import TransferStatus, User
from nft_gift_bot.services.crypto import SecretBox

logger = logging.getLogger(__name__)
router = Router(name="gifts")
intent_router = Router(name="gift_intents")  # registered last: catches free text


class TransferStates(StatesGroup):
    waiting_recipient = State()


def _service(session: AsyncSession, gift_api: GiftApi, box: SecretBox) -> GiftService:
    return GiftService(session, gift_api, box)


@router.message(F.text == MENU_GIFTS)
@router.callback_query(GiftCb.filter(F.action == "list"))
async def list_gifts(
    event: Message | CallbackQuery, session: AsyncSession, gift_api: GiftApi, box: SecretBox, db_user: User, emoji: dict
) -> None:
    service = _service(session, gift_api, box)
    now = utcnow()
    try:
        gifts = await service.refresh_gifts(db_user.id, now)
    except GiftAccessError as exc:
        await respond(event, texts.error(emoji, texts.gift_error_text(exc.code, exc.detail)))
        return
    except GiftApiError as exc:
        await respond(event, texts.error(emoji, exc.user_message))
        return
    await respond(event, texts.gift_list(emoji, gifts, now), inline.gift_list(gifts))


@router.callback_query(GiftCb.filter(F.action == "open"))
async def open_gift(
    cb: CallbackQuery, callback_data: GiftCb, session: AsyncSession, gift_api: GiftApi, box: SecretBox, db_user: User, emoji: dict
) -> None:
    service = _service(session, gift_api, box)
    now = utcnow()
    try:
        gift = await service.get_gift(db_user.id, callback_data.id, now)
    except GiftAccessError as exc:
        await cb.answer(texts.gift_error_text(exc.code, exc.detail), show_alert=True)
        return
    try:
        service.check_transferable(gift, now)
        transferable = True
    except GiftAccessError:
        transferable = False
    if gift.sticker_file_id and isinstance(cb.message, Message):
        try:
            await cb.message.answer_sticker(gift.sticker_file_id)
        except TelegramAPIError:
            logger.info("gift sticker unavailable")
    await respond(cb, texts.gift_card(emoji, gift, now), inline.gift_card(gift, transferable))


@router.callback_query(GiftCb.filter(F.action == "transfer"))
async def start_transfer(
    cb: CallbackQuery, callback_data: GiftCb, state: FSMContext, session: AsyncSession, gift_api: GiftApi,
    box: SecretBox, db_user: User, emoji: dict,
) -> None:
    service = _service(session, gift_api, box)
    now = utcnow()
    try:
        gift = await service.get_gift(db_user.id, callback_data.id, now)
        service.check_transferable(gift, now)
    except GiftAccessError as exc:
        await cb.answer(texts.gift_error_text(exc.code, exc.detail), show_alert=True)
        return
    await state.set_state(TransferStates.waiting_recipient)
    await state.update_data(gift_id=gift.id)
    await respond(cb, texts.ask_recipient(emoji, gift), inline.recipient_prompt())


@router.callback_query(GiftCb.filter(F.action == "abort"))
async def abort(cb: CallbackQuery, state: FSMContext, emoji: dict) -> None:
    await state.clear()
    await respond(cb, texts.notice(emoji, "gift", "Передача отменена"), edit=True)


async def _prepare_and_preview(
    message: Message, gift_id: int, recipient: RecipientRef, session: AsyncSession, gift_api: GiftApi,
    box: SecretBox, settings: Settings, db_user: User, emoji: dict,
) -> None:
    ttl = settings.transfer_confirm_ttl_seconds
    try:
        preview = await _service(session, gift_api, box).prepare_transfer(
            db_user.id, gift_id, recipient, utcnow(), timedelta(seconds=ttl)
        )
    except GiftAccessError as exc:
        await respond(message, texts.error(emoji, texts.gift_error_text(exc.code, exc.detail)))
        return
    await respond(message, texts.transfer_preview(emoji, preview, ttl), inline.transfer_confirm(preview.transfer.id))


@router.message(TransferStates.waiting_recipient, F.text, ~F.text.in_(MENU_ITEMS))
async def recipient_entered(
    message: Message, state: FSMContext, session: AsyncSession, gift_api: GiftApi, box: SecretBox,
    settings: Settings, db_user: User, emoji: dict,
) -> None:
    recipient = parse_recipient(message.text or "")
    if recipient is None:
        await respond(message, texts.error(emoji, texts.gift_error_text("bad_recipient")), inline.recipient_prompt())
        return
    data = await state.get_data()
    await state.clear()
    await _prepare_and_preview(message, int(data.get("gift_id", 0)), recipient, session, gift_api, box, settings, db_user, emoji)


@router.callback_query(GiftCb.filter(F.action == "confirm"))
async def confirm(
    cb: CallbackQuery, callback_data: GiftCb, session: AsyncSession, gift_api: GiftApi, box: SecretBox,
    settings: Settings, db_user: User, emoji: dict,
) -> None:
    # Remove the buttons first so the owner sees the tap was accepted.
    if isinstance(cb.message, Message):
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass
    try:
        transfer = await _service(session, gift_api, box).confirm(db_user.id, callback_data.id, utcnow())
    except GiftAccessError as exc:
        await respond(cb, texts.error(emoji, texts.gift_error_text(exc.code, exc.detail)))
        return
    await respond(cb, texts.transfer_result(emoji, transfer))
    if transfer.status == TransferStatus.FAILED:
        await notify_admins(
            cb.bot, settings.admin_id_set,
            f"⚠️ Ошибка передачи #{transfer.id}: {transfer.error_code} (пользователь {db_user.telegram_id})",
        )


@router.callback_query(GiftCb.filter(F.action == "cancel"))
async def cancel(cb: CallbackQuery, callback_data: GiftCb, session: AsyncSession, gift_api: GiftApi, box: SecretBox, db_user: User, emoji: dict) -> None:
    if await _service(session, gift_api, box).cancel(db_user.id, callback_data.id):
        await respond(cb, texts.notice(emoji, "gift", "Передача отменена"), edit=True)
    else:
        await cb.answer("Операция уже обработана.", show_alert=True)


@router.message(F.text == MENU_HISTORY)
async def history(message: Message, session: AsyncSession, gift_api: GiftApi, box: SecretBox, db_user: User, emoji: dict) -> None:
    transfers = await _service(session, gift_api, box).history(db_user.id, 10)
    await respond(message, texts.history(emoji, transfers))


async def _handle_intent(
    message: Message, text: str, session: AsyncSession, gift_api: GiftApi, box: SecretBox,
    settings: Settings, db_user: User, emoji: dict,
) -> bool:
    intent = parse_transfer_intent(text)
    if intent is None:
        return False
    service = _service(session, gift_api, box)
    try:
        matches = await service.find_gifts(db_user.id, intent.gift_query, utcnow())
    except GiftAccessError as exc:
        await respond(message, texts.error(emoji, texts.gift_error_text(exc.code, exc.detail)))
        return True
    if not matches and intent.nft_slug:
        await respond(message, texts.error(emoji, f"NFT {intent.nft_slug} не найден на вашем подключённом аккаунте. "
                                                   "Передать можно только свой подарок. Обновите «🎁 Мои NFT-подарки»."))
    elif not matches:
        await respond(message, texts.error(emoji, "Подарок не найден. Откройте «🎁 Мои NFT-подарки» и укажите номер из списка."))
    elif len(matches) > 1:
        await respond(
            message,
            texts.notice(emoji, "gift", "Найдено несколько подарков", "Уточните номер подарка или выберите его в списке."),
            inline.gift_list(matches),
        )
    else:
        await _prepare_and_preview(message, matches[0].id, intent.recipient, session, gift_api, box, settings, db_user, emoji)
    return True


@router.message(Command("transfer"))
async def transfer_command(
    message: Message, command: CommandObject, session: AsyncSession, gift_api: GiftApi, box: SecretBox,
    settings: Settings, db_user: User, emoji: dict,
) -> None:
    handled = await _handle_intent(message, f"/transfer {command.args or ''}", session, gift_api, box, settings, db_user, emoji)
    if not handled:
        await respond(message, texts.error(emoji, "Формат: /transfer <ссылка t.me/nft/… или номер подарка> <@получатель>\nПример: /transfer https://t.me/nft/PlushPepe-12 @username"))


@intent_router.message(F.text)
async def free_text(
    message: Message, session: AsyncSession, gift_api: GiftApi, box: SecretBox, settings: Settings, db_user: User, emoji: dict
) -> None:
    if not await _handle_intent(message, message.text or "", session, gift_api, box, settings, db_user, emoji):
        await respond(message, texts.notice(emoji, "brand", "Выберите действие в меню", "Или напишите: «передай <номер> @username»."))
