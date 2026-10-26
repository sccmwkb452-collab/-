"""Bot UI kit: compact cards, inline keyboards, pagination, confirmations.

Inline buttons use only what the Bot API supports: text with emoji and the
official ``style`` values (primary / success / danger) for the main action,
confirmations and destructive actions. Arbitrary button colours do not exist
in Telegram and are not used.
"""

from __future__ import annotations

import html
import math
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from ..shared.money import fmt_money, fmt_pct

SEP = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
HOME = "home"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def b(text: str, cb: str = "noop", *, style: str | None = None, url: str | None = None, copy: str | None = None) -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    if copy is not None:
        return InlineKeyboardButton(text=text, copy_text=CopyTextButton(text=copy[:256]))
    assert len(cb.encode()) <= 64, cb
    return InlineKeyboardButton(text=text, callback_data=cb, style=style)


def kb(*rows: Iterable[InlineKeyboardButton] | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def nav(back: str | None = None, *, home: bool = True) -> list[InlineKeyboardButton]:
    row = []
    if back:
        row.append(b("‹ Назад", back))
    if home:
        row.append(b("🏠 Меню", HOME))
    return row


def pager(prefix: str, page: int, total: int, per_page: int) -> list[InlineKeyboardButton]:
    pages = max(1, math.ceil(total / per_page))
    if pages <= 1:
        return []
    row = []
    if page > 1:
        row.append(b("◀️", f"{prefix}:{page - 1}"))
    row.append(b(f"{page}/{pages}", "noop"))
    if page < pages:
        row.append(b("▶️", f"{prefix}:{page + 1}"))
    return row


def confirm(text: str, yes_cb: str, no_cb: str, *, danger: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    return (
        f"❓ <b>Подтвердите действие</b>\n{SEP}\n{text}",
        kb([b("✅ Да, выполнить", yes_cb, style="danger" if danger else "success"), b("✖️ Отмена", no_cb)]),
    )


def title(icon: str, text: str, subtitle: str | None = None) -> str:
    head = f"{icon} <b>{esc(text)}</b>"
    return head + (f"\n<i>{esc(subtitle)}</i>" if subtitle else "") + f"\n{SEP}"


def line(label: str, value: Any) -> str:
    return f"{label}: <b>{esc(value)}</b>" if value not in (None, "") else f"{label}: —"


def money(value: Decimal | str | None) -> str:
    if value in (None, ""):
        return "—"
    return fmt_money(Decimal(str(value)))


def pct(value: Decimal | str | None) -> str:
    if value in (None, ""):
        return "—"
    return fmt_pct(Decimal(str(value)))


def short(text: str | None, limit: int = 32) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def onoff(value: bool) -> str:
    return "🟢 Вкл" if value else "⚪️ Выкл"


def empty(text: str) -> str:
    return f"<i>{esc(text)}</i>"
