from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.emoji import EMOJI


def _e(key: str) -> str:
    return EMOJI[key].char


def main_menu_kb(has_subscription: bool = False) -> InlineKeyboardMarkup:
    """
    Главное меню — 6 кнопок в тёмном премиальном стиле.

    Макет:
        [💎 Купить подписку]          ← или [💎 Моя подписка] если активна
        [🎁 Мои подарки] [🔗 Подключить аккаунт]
        [🛒 Купить Tdata] [👤 Профиль]
        [ℹ️ Информация и поддержка]
    """
    b = InlineKeyboardBuilder()

    # Строка 1 — подписка (адаптивная)
    if has_subscription:
        b.row(
            InlineKeyboardButton(
                text=f"{_e('crown')} Моя подписка",
                callback_data="sub:info",
            )
        )
    else:
        b.row(
            InlineKeyboardButton(
                text=f"{_e('diamond')} Купить подписку",
                callback_data="sub:plans",
            )
        )

    # Строка 2 — подарки + подключение
    b.row(
        InlineKeyboardButton(text=f"{_e('gift')} Мои подарки", callback_data="gifts:my"),
        InlineKeyboardButton(text=f"{_e('link')} Подключить аккаунт", callback_data="connect:info"),
    )

    # Строка 3 — tdata + профиль
    b.row(
        InlineKeyboardButton(text=f"{_e('cart')} Купить Tdata", callback_data="tdata:shop"),
        InlineKeyboardButton(text=f"{_e('profile')} Профиль", callback_data="profile:main"),
    )

    # Строка 4 — информация и поддержка
    b.row(
        InlineKeyboardButton(
            text=f"{_e('info')} Информация и поддержка",
            callback_data="info:main",
        )
    )

    return b.as_markup()


def back_kb(callback_data: str = "menu:main") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"{_e('back')} Главное меню", callback_data=callback_data)
    return b.as_markup()


def subscription_plans_kb() -> InlineKeyboardMarkup:
    """Кнопки выбора тарифного плана."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"{_e('gem_blue')} Basic",
            callback_data="sub:buy:basic",
        ),
        InlineKeyboardButton(
            text=f"{_e('crown')} Premium",
            callback_data="sub:buy:premium",
        ),
    )
    b.row(InlineKeyboardButton(text=f"{_e('back')} Назад", callback_data="menu:main"))
    return b.as_markup()


def connect_account_kb(status: str = "none") -> InlineKeyboardMarkup:
    """
    status:
      "none"      → show Connect button
      "connected" → show Disconnect button
      "pending"   → show Cancel button
    """
    b = InlineKeyboardBuilder()
    if status == "connected":
        b.row(InlineKeyboardButton(
            text=f"{_e('cross')} Отключить аккаунт",
            callback_data="connect:disconnect",
        ))
    elif status == "pending":
        b.row(InlineKeyboardButton(
            text=f"{_e('cross')} Отменить",
            callback_data="connect:cancel",
        ))
    else:
        b.row(InlineKeyboardButton(
            text=f"{_e('link')} Подключить аккаунт",
            callback_data="connect:start",
        ))
    b.row(InlineKeyboardButton(text=f"{_e('back')} Главное меню", callback_data="menu:main"))
    return b.as_markup()


def tdata_shop_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"{_e('support')} Написать менеджеру",
            callback_data="tdata:contact",
        )
    )
    b.row(InlineKeyboardButton(text=f"{_e('back')} Назад", callback_data="menu:main"))
    return b.as_markup()


def profile_kb(has_subscription: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not has_subscription:
        b.row(
            InlineKeyboardButton(
                text=f"{_e('diamond')} Купить подписку",
                callback_data="sub:plans",
            )
        )
    b.row(InlineKeyboardButton(text=f"{_e('back')} Назад", callback_data="menu:main"))
    return b.as_markup()


def ton_payment_kb(payment_comment: str) -> InlineKeyboardMarkup:
    """Keyboard shown while waiting for TON payment confirmation."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"{_e('check')} Я оплатил — проверить",
            callback_data=f"pay:check:{payment_comment}",
        )
    )
    b.row(InlineKeyboardButton(text=f"{_e('back')} Назад", callback_data="menu:main"))
    return b.as_markup()


def support_kb(support_username: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"{_e('support')} Написать в поддержку",
            url=f"https://t.me/{support_username}",
        )
    )
    b.row(InlineKeyboardButton(text=f"{_e('back')} Назад", callback_data="menu:main"))
    return b.as_markup()
