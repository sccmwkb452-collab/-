"""Тексты и клавиатуры панели."""
from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import Cb
from app.db.models import Contact, Deal, DealStatus, Owner

MAIN_MENU = [
    ("🤖 ИИ-агент", "agent"),
    ("🔗 Подключение Business", "biz"),
    ("🔎 Парсеры", "parsers"),
    ("💬 Начальный текст", "tpl"),
    ("🧠 Настройки ИИ", "ai"),
    ("🛍 Торговый бот", "trade"),
    ("🤝 Управление сделками", "deals"),
    ("📁 Медиа и материалы", "media"),
    ("📊 Статистика", "stats"),
    ("📜 История действий", "log"),
    ("⏸ Приостановить работу", "pause"),
    ("▶️ Возобновить работу", "resume"),
    ("⚙️ Настройки", "settings"),
]

STATUS_RU = {
    DealStatus.DRAFT: "черновик",
    DealStatus.AWAITING_CONFIRMATION: "ждёт подтверждения",
    DealStatus.CONFIRMED: "подтверждена",
    DealStatus.CREATING: "создаётся",
    DealStatus.CREATED: "создана",
    DealStatus.USER_ACTION_REQUIRED: "нужно действие в торговом боте",
    DealStatus.PAYING: "оплачивается",
    DealStatus.PAID: "оплачена",
    DealStatus.COMPLETED: "завершена",
    DealStatus.CANCELLED: "отменена",
    DealStatus.FAILED: "ошибка",
    DealStatus.UNKNOWN: "результат неизвестен — сверка",
}


def btn(text: str, s: str, a: str = "show", i: int = 0, v: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=Cb(s=s, a=a, i=i, v=v).pack())


def kb(*rows: list[InlineKeyboardButton], back: str | None = "main") -> InlineKeyboardMarkup:
    rows_list = [list(r) for r in rows if r]
    if back:
        rows_list.append([btn("⬅️ Назад" if back != "main" else "🏠 Главное меню", back)])
    return InlineKeyboardMarkup(inline_keyboard=rows_list)


def main_menu(owner: Owner, is_admin: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for text, section in MAIN_MENU:
        if section == "pause" and owner.paused or section == "resume" and not owner.paused:
            continue
        b.add(btn(text, section))
    if is_admin:
        b.add(btn("🛡 Администратор", "admin"))
    b.adjust(2)
    return b.as_markup()


def onoff(flag: bool) -> str:
    return "✅ вкл" if flag else "⛔️ выкл"


def contact_title(contact: Contact | None) -> str:
    if contact is None:
        return "—"
    name = escape(contact.display_name or "без имени")
    return f"{name} (@{contact.username})" if contact.username else name


def deal_card(deal: Deal, contact: Contact | None) -> str:
    item = deal.item or {}
    attrs = "; ".join(f"{escape(str(k))}: {escape(str(v))}" for k, v in (item.get("attributes") or {}).items())
    side = "Покупка у продавца" if deal.side == "buy" else "Продажа покупателю"
    lines = [
        f"<b>Сделка #{deal.id}</b> — {side}",
        f"Контрагент: {contact_title(contact)}",
        f"Товар: {escape(item.get('description') or deal.product_type or '—')}",
    ]
    if attrs:
        lines.append(f"Характеристики: {attrs}")
    lines += [
        f"Количество: {deal.quantity}",
        f"Цена: {deal.unit_price.normalize()} {deal.currency}",
        f"Комиссии (оценка по настройкам бота): {deal.fees.normalize()} {deal.currency}",
        f"<b>Итого: {deal.total.normalize()} {deal.currency}</b>",
        f"Торговый бот: @{escape(deal.trade_bot_username or '—')} (ID {deal.trade_bot_user_id})",
        f"Статус: {STATUS_RU.get(DealStatus(deal.status), deal.status)}",
    ]
    if deal.external_url:
        lines.append(f"Ссылка: {escape(deal.external_url)}")
    if deal.last_error:
        lines.append(f"Последняя ошибка: {escape(deal.last_error)}")
    if item.get("instructions"):
        lines.append("\n" + escape(item["instructions"]))
    return "\n".join(lines)


def deal_actions(deal: Deal) -> InlineKeyboardMarkup:
    s = DealStatus(deal.status)
    rows = []
    if s == DealStatus.AWAITING_CONFIRMATION:
        rows.append([btn("✅ Подтвердить и создать", "deals", "confirm", deal.id), btn("✖️ Отменить", "deals", "cancel", deal.id)])
    if s == DealStatus.CREATED and deal.side == "buy":
        rows.append([btn("💸 Оплатить", "deals", "pay", deal.id)])
    if s in (DealStatus.UNKNOWN, DealStatus.PAYING, DealStatus.CREATED):
        rows.append([btn("🔄 Сверить статус", "deals", "reconcile", deal.id)])
    if s == DealStatus.UNKNOWN and deal.payment_spend_id:
        rows.append([btn("↻ Повторить с тем же spend_id", "deals", "retry_ask", deal.id)])
    if s == DealStatus.USER_ACTION_REQUIRED:
        rows.append([btn("✔️ Создана в боте", "deals", "mark", deal.id, "created"),
                     btn("💰 Оплачена", "deals", "mark", deal.id, "paid")])
    if s in (DealStatus.PAID, DealStatus.CREATED, DealStatus.USER_ACTION_REQUIRED):
        rows.append([btn("🏁 Завершена (товар получен)", "deals", "mark", deal.id, "completed")])
    if s in (DealStatus.CREATED, DealStatus.USER_ACTION_REQUIRED, DealStatus.CONFIRMED):
        rows.append([btn("✖️ Отменить", "deals", "cancel", deal.id)])
    return kb(*rows, back="deals")
