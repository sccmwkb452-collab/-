"""Extra buttons of the bot's main menu, created in the admin panel.

Every action is data, not code: a text to send, a page of the Mini App from a
fixed list, an https link, a section of the bot or a package. The bot reads
the buttons from the database each time it draws the menu, so a change shows
up at once, with no restart.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import BotButtonAction, ButtonStyle
from ..database.models import BotButton, Product
from ..shared.errors import ValidationFailed

# Sections of the bot a button can open.
BOT_SECTIONS = {
    "buy": "Купить Stars",
    "profile": "Профиль",
    "orders": "Мои заказы",
    "referrals": "Реферальная программа",
    "support": "Поддержка",
}
# Pages of the Mini App a button can open.
WEBAPP_PAGES = {
    "/": "Главная магазина",
    "/catalog": "Пакеты Stars",
    "/lucky": "Lucky Buy",
    "/orders": "Мои заказы",
    "/profile": "Профиль",
    "/referrals": "Реферальная программа",
    "/support": "Поддержка",
}
MAX_BUTTONS = 30


def options() -> dict[str, Any]:
    return {
        "actions": [a.value for a in BotButtonAction],
        "styles": [s.value for s in ButtonStyle],
        "sections": [{"id": k, "title": v} for k, v in BOT_SECTIONS.items()],
        "pages": [{"path": k, "title": v} for k, v in WEBAPP_PAGES.items()],
    }


def check_url(url: str | None) -> str:
    value = (url or "").strip()
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.netloc or any(c.isspace() for c in value) or len(value) > 512:
        raise ValidationFailed("Ссылка должна начинаться с https:// и не содержать пробелов", code="bot_button_url_invalid")
    return value


async def normalize(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    """Validates a button and drops the fields its action does not use."""
    action = BotButtonAction(data["action"])
    title = (data.get("title") or "").strip()
    if not title:
        raise ValidationFailed("Укажите название кнопки", code="bot_button_title_required")
    clean: dict[str, Any] = {
        "title": title,
        "emoji": (data.get("emoji") or "").strip() or None,
        "row": data.get("row", 0),
        "position": data.get("position", 0),
        "is_active": data.get("is_active", True),
        "action": action,
        "style": ButtonStyle(data["style"]) if data.get("style") else None,
        "text": None,
        "url": None,
        "section": None,
        "product_id": None,
    }
    if action == BotButtonAction.message:
        text = (data.get("text") or "").strip()
        if not text:
            raise ValidationFailed("Укажите текст сообщения", code="bot_button_text_required")
        clean["text"] = text[:2000]
    elif action == BotButtonAction.url:
        clean["url"] = check_url(data.get("url"))
    elif action == BotButtonAction.webapp:
        path = data.get("url") or "/"
        if path not in WEBAPP_PAGES:
            raise ValidationFailed("Выберите страницу магазина из списка", code="bot_button_page_invalid")
        clean["url"] = path
    elif action == BotButtonAction.section:
        if data.get("section") not in BOT_SECTIONS:
            raise ValidationFailed("Выберите раздел бота из списка", code="bot_button_section_invalid")
        clean["section"] = data["section"]
    elif action == BotButtonAction.product:
        product = await session.get(Product, data.get("product_id") or 0)
        if product is None or product.is_archived:
            raise ValidationFailed("Выберите пакет из каталога", code="bot_button_product_invalid")
        clean["product_id"] = product.id
        clean["text"] = (data.get("text") or "").strip()[:2000] or None
    return clean


async def active_buttons(session: AsyncSession) -> list[BotButton]:
    rows = await session.execute(
        select(BotButton).where(BotButton.is_active.is_(True)).order_by(BotButton.row, BotButton.position, BotButton.id).limit(MAX_BUTTONS)
    )
    return list(rows.scalars())


def serialize(b: BotButton) -> dict[str, Any]:
    return {
        "id": b.id,
        "title": b.title,
        "emoji": b.emoji,
        "row": b.row,
        "position": b.position,
        "is_active": b.is_active,
        "action": b.action,
        "style": b.style,
        "text": b.text,
        "url": b.url,
        "section": b.section,
        "product_id": b.product_id,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }
