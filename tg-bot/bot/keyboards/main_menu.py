from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="💎 Купить подписку",
            callback_data="menu:subscription",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🎁 NFT-подарки",
            callback_data="menu:nft_gifts",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 Мой аккаунт",
            callback_data="menu:account",
        ),
        InlineKeyboardButton(
            text="📋 История операций",
            callback_data="menu:history",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🆘 Поддержка",
            callback_data="menu:support",
        )
    )

    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Главное меню", callback_data="menu:main")
    return builder.as_markup()
