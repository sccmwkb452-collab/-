"""Раздел «Мои подарки» — коллекция NFT пользователя."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_kb
from bot.ui.rich_text import RichTextBuilder, e
from bot.ui.templates import gifts_empty, gifts_list_header
from config.emoji import EMOJI
from database.models.gift import Gift, GiftRarity, GiftStatus
from database.models.user import User

logger = logging.getLogger(__name__)
router = Router(name="gifts")

RARITY_BADGE = {
    GiftRarity.COMMON:    "⚪",
    GiftRarity.RARE:      "🔵",
    GiftRarity.EPIC:      "🟣",
    GiftRarity.LEGENDARY: "🟡",
}


@router.callback_query(F.data == "gifts:my")
async def cb_gifts_my(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    result = await session.execute(
        select(Gift)
        .where(Gift.owner_id == db_user.id, Gift.status == GiftStatus.OWNED)
        .order_by(Gift.created_at.desc())
        .limit(20)
    )
    gifts = result.scalars().all()

    if not gifts:
        text, entities = gifts_empty()
        await callback.message.edit_text(
            text=text,
            entities=entities,
            reply_markup=back_kb(),
        )
        await callback.answer()
        return

    text, entities = gifts_list_header(len(gifts))

    # Строим кнопки для каждого подарка
    b = InlineKeyboardBuilder()
    for gift in gifts:
        badge = RARITY_BADGE.get(gift.rarity, "⚪")
        label = f"{badge} {gift.name[:24]}"
        b.button(text=label, callback_data=f"gifts:detail:{gift.id}")
    b.adjust(2)  # 2 кнопки в ряд
    b.row(InlineKeyboardButton(text=f"{e('back')} Назад", callback_data="menu:main"))

    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gifts:detail:"))
async def cb_gift_detail(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    gift_id = int(callback.data.split(":")[-1])
    gift = await session.get(Gift, gift_id)

    if not gift or gift.owner_id != db_user.id:
        await callback.answer("Подарок не найден.", show_alert=True)
        return

    badge = RARITY_BADGE.get(gift.rarity, "⚪")

    rt = RichTextBuilder()
    rt.custom_emoji("gift").text(" ").bold(gift.name).newline()
    rt.text("─" * 26).newline(2)
    rt.text(f"{badge} Редкость: ").bold(gift.rarity.value.title()).newline()
    if gift.serial_number and gift.total_supply:
        rt.text(f"{e('stats')} Серийный №: ").bold(f"{gift.serial_number} / {gift.total_supply}").newline()
    if gift.description:
        rt.newline().italic(gift.description).newline()
    rt.newline()
    if gift.is_transferable:
        rt.text(f"{e('check')} Можно передать другому пользователю")
    else:
        rt.text(f"{e('lock')} Передача заблокирована")

    text, entities = rt.build()

    b = InlineKeyboardBuilder()
    if gift.is_transferable:
        b.row(
            InlineKeyboardButton(
                text=f"{e('arrow_right')} Передать",
                callback_data=f"gifts:transfer:{gift.id}",
            )
        )
    b.row(InlineKeyboardButton(text=f"{e('back')} Назад", callback_data="gifts:my"))

    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gifts:transfer:"))
async def cb_gift_transfer(
    callback: CallbackQuery,
    db_user: User,
) -> None:
    await callback.answer(
        "🔗 Функция передачи подарков будет доступна после подключения аккаунта.",
        show_alert=True,
    )
