from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb(has_subscription: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if has_subscription:
        builder.row(
            InlineKeyboardButton(text="💎 Моя подписка", callback_data="sub:info")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🚀 Купить подписку", callback_data="sub:plans")
        )

    builder.row(
        InlineKeyboardButton(text="🎁 NFT-подарки", callback_data="gifts:catalog")
    )
    builder.row(
        InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="account:info"),
        InlineKeyboardButton(text="📋 История", callback_data="account:history"),
    )
    builder.row(
        InlineKeyboardButton(text="🆘 Поддержка", callback_data="support:main")
    )

    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Главное меню", callback_data="menu:main")
    return builder.as_markup()
