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
from ..services.app_settings import RuntimeSettings
from .emoji import ICON_FALLBACK, emoji_id

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


def _icon(text: str, icon: str | None) -> tuple[str, str | None]:
    """With a custom emoji icon the leading usual emoji is dropped (Telegram
    shows the icon in its place); it comes back if Telegram refuses the icon."""
    if not icon:
        return text, None
    head, _, rest = text.partition(" ")
    if rest and not head.isalnum():
        ICON_FALLBACK[icon] = head
        return rest, icon
    return text, icon


def button(
    text: str, *, callback: str | None = None, url: str | None = None, style: str | None = None, icon: str | None = None
) -> InlineKeyboardButton:
    text, icon = _icon(text, icon)
    return InlineKeyboardButton(text=text, callback_data=callback, url=url, style=style, icon_custom_emoji_id=icon)


def webapp_button(text: str, path: str = "", *, style: str | None = None, icon: str | None = None) -> InlineKeyboardButton:
    if can_use_webapp():
        text, icon = _icon(text, icon)
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url(path)), style=style, icon_custom_emoji_id=icon)
    return InlineKeyboardButton(text=text, callback_data="nohttps", style=style)


def support_url(username: str | None) -> str | None:
    """The support account as a t.me link (Admin → Контент → Поддержка)."""
    name = (username or "").strip().removeprefix("https://t.me/").lstrip("@").strip("/")
    return f"https://t.me/{name}" if name and name.replace("_", "").isalnum() else None


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


def main_menu(extra: Iterable[BotButton] = (), *, runtime: RuntimeSettings | None = None, premium: bool = False) -> InlineKeyboardMarkup:
    """One button opens the shop (Mini App); purchases also work right in the chat."""

    def ic(key: str) -> str | None:
        return emoji_id(runtime, key)

    support = support_url(runtime.content.support.telegram) if runtime else None
    buy_row = [button("⭐️ Купить Stars", callback="buy:start", style="success", icon=ic("stars"))]
    if premium:
        buy_row.append(button("💎 Premium", callback="buy:premium", style="success", icon=ic("premium")))
    rows = [
        [webapp_button("🌐 Открыть магазин", style="primary", icon=ic("shop"))],
        buy_row,
        [
            button("👤 Профиль", callback="menu:profile", icon=ic("profile")),
            button("🧾 Мои заказы", callback="menu:orders", icon=ic("orders")),
        ],
        [
            button("🎁 Рефералы", callback="menu:referrals", icon=ic("referrals")),
            button("💬 Поддержка", url=support, icon=ic("support"))
            if support
            else button("💬 Поддержка", callback="menu:support", icon=ic("support")),
        ],
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
