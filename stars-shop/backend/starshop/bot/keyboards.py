from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..config import get_settings


def webapp_url(path: str = "") -> str:
    return get_settings().webapp_url.rstrip("/") + ("/" + path.lstrip("/") if path else "/")


def can_use_webapp() -> bool:
    # Telegram accepts Mini App buttons only with HTTPS URLs.
    return get_settings().webapp_url.startswith("https://")


def webapp_button(text: str, path: str = "") -> InlineKeyboardButton:
    if can_use_webapp():
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url(path)))
    return InlineKeyboardButton(text=text, callback_data="nohttps")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [webapp_button("✨ Открыть магазин")],
            [webapp_button("✨ Купить Stars", "catalog"), InlineKeyboardButton(text="👤 Мой профиль", callback_data="menu:profile")],
            [
                InlineKeyboardButton(text="🧾 Мои заказы", callback_data="menu:orders"),
                InlineKeyboardButton(text="💳 Способы оплаты", callback_data="menu:payments"),
            ],
            [
                InlineKeyboardButton(text="🎁 Бонусы", callback_data="menu:bonus"),
                InlineKeyboardButton(text="💬 Поддержка", callback_data="menu:support"),
            ],
        ]
    )


def back_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:home")]


def with_back(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[*rows, back_row()])


def support_waiting() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="support:cancel")]])
