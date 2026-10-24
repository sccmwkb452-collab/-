"""Keyboards of the bot.

Button colours use the ``style`` field of the Bot API: ``primary`` (blue) for
the main action, ``success`` (green) for confirmation and payment, ``danger``
(red) for cancelling. Clients without support show the usual style.
"""

from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..config import get_settings
from ..database.enums import BotButtonAction
from ..database.models import BotButton

SECTION_CALLBACKS = {
    "buy": "buy:start",
    "profile": "menu:profile",
    "orders": "menu:orders",
    "referrals": "menu:referrals",
    "support": "menu:support",
}


def webapp_url(path: str = "") -> str:
    return get_settings().webapp_url.rstrip("/") + ("/" + path.lstrip("/") if path else "/")


def can_use_webapp() -> bool:
    # Telegram accepts Mini App buttons only with HTTPS URLs.
    return get_settings().webapp_url.startswith("https://")


def button(text: str, *, callback: str | None = None, url: str | None = None, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback, url=url, style=style)


def webapp_button(text: str, path: str = "", *, style: str | None = None) -> InlineKeyboardButton:
    if can_use_webapp():
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url(path)), style=style)
    return InlineKeyboardButton(text=text, callback_data="nohttps", style=style)


def custom_button(b: BotButton) -> InlineKeyboardButton:
    text = f"{b.emoji} {b.title}" if b.emoji else b.title
    style = b.style.value if b.style else None
    if b.action == BotButtonAction.url and b.url:
        return button(text, url=b.url, style=style)
    if b.action == BotButtonAction.webapp:
        return webapp_button(text, b.url or "", style=style)
    if b.action == BotButtonAction.section and b.section in SECTION_CALLBACKS:
        return button(text, callback=SECTION_CALLBACKS[b.section], style=style)
    return button(text, callback=f"cb:{b.id}", style=style)


def main_menu(extra: Iterable[BotButton] = ()) -> InlineKeyboardMarkup:
    """One button opens the shop (Mini App); purchases also work right in the chat."""
    rows = [
        [webapp_button("🌐 Открыть магазин", style="primary")],
        [button("⭐️ Купить Stars", callback="buy:start", style="success")],
        [button("👤 Профиль", callback="menu:profile"), button("🧾 Мои заказы", callback="menu:orders")],
        [button("🎁 Рефералы", callback="menu:referrals"), button("💬 Поддержка", callback="menu:support")],
    ]
    by_row: dict[int, list[BotButton]] = {}
    for b in extra:
        by_row.setdefault(b.row, []).append(b)
    for row in sorted(by_row):
        rows.append([custom_button(b) for b in sorted(by_row[row], key=lambda b: (b.position, b.id))][:4])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_row() -> list[InlineKeyboardButton]:
    return [button("◀️ В меню", callback="menu:home")]


def with_back(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[*rows, back_row()])


def support_waiting() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[button("✖️ Отмена", callback="support:cancel", style="danger")]])
