from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MENU_SUBSCRIPTION = "💎 Купить подписку"
MENU_GIFTS = "🎁 Мои NFT-подарки"
MENU_CONNECT = "🔐 Подключить аккаунт"
MENU_CABINET = "👤 Личный кабинет"
MENU_PAYMENTS = "💳 Мои платежи"
MENU_HISTORY = "📜 История операций"
MENU_SETTINGS = "⚙️ Настройки"
MENU_SUPPORT = "🆘 Поддержка"

MENU_ITEMS = (
    MENU_SUBSCRIPTION,
    MENU_GIFTS,
    MENU_CONNECT,
    MENU_CABINET,
    MENU_PAYMENTS,
    MENU_HISTORY,
    MENU_SETTINGS,
    MENU_SUPPORT,
)


def main_menu() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=a), KeyboardButton(text=b)] for a, b in zip(MENU_ITEMS[::2], MENU_ITEMS[1::2], strict=True)]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
