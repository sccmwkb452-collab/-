from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.emoji import EMOJI
from database.models.shop import ShopOrder, ShopProduct


def _e(key: str) -> str:
    return EMOJI[key].char


def catalog_kb(products: list[ShopProduct]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in products:
        b.row(
            InlineKeyboardButton(
                text=f"{p.title} — {float(p.price_ton):.2f} TON",
                callback_data=f"shop:product:{p.id}",
            )
        )
    b.row(InlineKeyboardButton(text=f"{_e('back')} Главное меню", callback_data="menu:main"))
    return b.as_markup()


def product_kb(product_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"{_e('cart')} Купить",
            callback_data=f"shop:buy:{product_id}",
        )
    )
    b.row(
        InlineKeyboardButton(text=f"{_e('back')} Назад", callback_data="shop:catalog"),
    )
    return b.as_markup()


def order_payment_kb(payment_comment: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"{_e('check')} Я оплатил — проверить",
            callback_data=f"shop:check:{payment_comment}",
        )
    )
    b.row(InlineKeyboardButton(text=f"{_e('back')} Мои заказы", callback_data="shop:my_orders"))
    return b.as_markup()


def my_orders_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"{_e('back')} Главное меню", callback_data="menu:main"))
    return b.as_markup()


def empty_catalog_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"{_e('back')} Главное меню", callback_data="menu:main"))
    return b.as_markup()
