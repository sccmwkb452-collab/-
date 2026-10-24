"""Telegram message templates (HTML parse mode)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from html import escape
from typing import Any

from ..config import get_settings
from ..database.models import LuckyDraw, Order
from ..services.lucky import percent_str, roll_str, ru
from ..shared.items import item_line
from ..shared.masking import mask_username

STATUS_LABELS = {
    "created": "Создан",
    "pending_payment": "Ожидает оплаты",
    "paid": "Оплачен",
    "processing": "В обработке",
    "completed": "Выполнен",
    "failed": "Требует внимания",
    "refund_pending": "Оформляется возврат",
    "refunded": "Возврат выполнен",
    "cancelled": "Отменён",
    "lost": "Не повезло",
}


@dataclass(slots=True)
class Message:
    text: str
    reply_markup: dict[str, Any] | None = None


def fmt_money(amount: Decimal, currency: str) -> str:
    if currency == "XTR":  # Telegram Stars
        return f"{fmt_stars(int(amount))} ⭐️"
    symbols = {"RUB": "₽", "USD": "$", "EUR": "€", "KZT": "₸", "UAH": "₴", "BYN": "Br"}
    value = f"{amount:,.2f}".replace(",", "\u202f")
    value = value[:-3] if value.endswith(".00") else value.replace(".", ",")
    sym = symbols.get(currency)
    return f"{value} {sym}" if sym else f"{value} {currency}"


def fmt_stars(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def order_url(order: Order) -> str:
    return f"{get_settings().webapp_url.rstrip('/')}/orders/{order.id}"


def order_button(order: Order, text: str = "Посмотреть заказ") -> dict[str, Any]:
    return {"text": text, "web_app": {"url": order_url(order)}}


def recipient_line(order: Order) -> str:
    if order.recipient_type == "self":
        return "себе"
    return escape(mask_username(order.recipient_username))


def item(order: Order) -> str:
    return item_line(order.stars_amount, order.premium_months)


def _demo_suffix(order: Order) -> str:
    return "\n\n<i>DEMO · тестовый заказ, реальные Stars и Premium не отправляются.</i>" if order.mode == "demo" else ""


def awaiting_payment(order: Order, pay_url: str | None, pay_url_kind: str | None) -> Message:
    text = (
        f"🧾 <b>Заказ #{order.number} создан</b>\n"
        f"{item(order)} → {recipient_line(order)}\n"
        f"К оплате: <b>{fmt_money(order.total, order.currency)}</b>\n\n"
        "Ожидаем оплату. Заказ уйдёт в работу сразу после подтверждения платежа провайдером." + _demo_suffix(order)
    )
    buttons: list[list[dict[str, Any]]] = []
    if pay_url and pay_url_kind in ("telegram", "external", "invoice"):
        buttons.append([{"text": "💳 Оплатить", "url": pay_url}])
    buttons.append([order_button(order)])
    return Message(text, {"inline_keyboard": buttons})


def payment_confirmed(order: Order) -> Message:
    return Message(
        f"✅ <b>Оплата подтверждена</b>\nЗаказ #{order.number} · {fmt_money(order.total, order.currency)}\n"
        "Передаём заказ на доставку." + _demo_suffix(order),
        {"inline_keyboard": [[order_button(order)]]},
    )


def _chance(draw: LuckyDraw) -> str:
    return ru(percent_str(draw.chance_bp))


def _roll(draw: LuckyDraw) -> str:
    return ru(roll_str(draw.roll_bp or 0))


def lucky_won(order: Order, draw: LuckyDraw) -> Message:
    return Message(
        f"🍀 <b>Вам повезло!</b>\n"
        f"Lucky Buy #{order.number} · шанс {_chance(draw)}%\n"
        f"Выпало <b>{_roll(draw)}</b> — нужно было меньше {_chance(draw)}.\n\n"
        f"{item(order)} → {recipient_line(order)}. Передаём заказ на доставку." + _demo_suffix(order),
        {"inline_keyboard": [[order_button(order)]]},
    )


def lucky_lost(order: Order, draw: LuckyDraw) -> Message:
    return Message(
        f"🎲 <b>В этот раз не повезло</b>\n"
        f"Lucky Buy #{order.number} · шанс {_chance(draw)}% на {fmt_stars(order.stars_amount)} Stars\n"
        f"Выпало <b>{_roll(draw)}</b> — нужно было меньше {_chance(draw)}.\n\n"
        "Оплата попытки не возвращается. Проверить честность розыгрыша можно в карточке заказа." + _demo_suffix(order),
        {"inline_keyboard": [[order_button(order)]]},
    )


def processing(order: Order) -> Message:
    return Message(
        f"⚙️ <b>Заказ #{order.number} в обработке</b>\n{item(order)} → {recipient_line(order)}",
        {"inline_keyboard": [[order_button(order)]]},
    )


def delivered(order: Order) -> Message:
    if order.mode == "demo":
        text = f"🧪 <b>DEMO-заказ #{order.number} выполнен</b>\nЭто тестовый сценарий: {'Premium не подключался' if order.premium_months else 'реальные Stars не отправлялись'}."
    else:
        if order.premium_months:
            head = f"💎 <b>Telegram Premium подключён!</b>\n{item(order)} — получатель {recipient_line(order)}.\n"
        elif order.kind == "withdrawal":
            head = f"💸 <b>Вывод выполнен!</b>\n{item(order)} зачислены на ваш аккаунт.\n"
        else:
            head = f"🌟 <b>Stars доставлены!</b>\n{item(order)} зачислены получателю ({recipient_line(order)}).\n"
        text = head + f"Заказ #{order.number} выполнен. Спасибо за покупку!"
    return Message(text, {"inline_keyboard": [[order_button(order)]]})


def problem(order: Order) -> Message:
    return Message(
        f"⚠️ <b>С заказом #{order.number} возникла проблема</b>\nМы уже разбираемся. Если заказ не будет выполнен, оформим возврат оплаты.",
        {"inline_keyboard": [[order_button(order)]]},
    )


def refund_requested(order: Order) -> Message:
    return Message(
        f"↩️ <b>Оформлен возврат по заказу #{order.number}</b>\n"
        f"Сумма: {fmt_money(order.total, order.currency)}. Сообщим, когда провайдер подтвердит возврат.",
        {"inline_keyboard": [[order_button(order)]]},
    )


def refunded(order: Order) -> Message:
    return Message(
        f"💸 <b>Возврат выполнен</b>\nЗаказ #{order.number} · {fmt_money(order.total, order.currency)}",
        {"inline_keyboard": [[order_button(order)]]},
    )


def order_expired(order: Order) -> Message:
    return Message(
        f"⌛️ Время на оплату заказа #{order.number} истекло, заказ отменён.\nОформите новый заказ в магазине — это займёт минуту.",
        None,
    )


def support_reply(ticket_id: int, text: str) -> Message:
    return Message(
        f"💬 <b>Ответ поддержки</b> · обращение #{ticket_id}\n\n{escape(text)}\n\n"
        "<i>Чтобы ответить, нажмите «💬 Поддержка» в меню бота.</i>",
        None,
    )


# --- admin alerts ------------------------------------------------------------


def admin_paid_order(order: Order, username: str | None, draw: LuckyDraw | None = None) -> Message:
    who = f"@{escape(username)}" if username else "без username"
    lucky = ""
    if draw is not None:
        outcome = "выигрыш, Stars уходят на доставку" if draw.won else "без выигрыша"
        lucky = f"\n🍀 Lucky Buy · шанс {_chance(draw)}% · выпало {_roll(draw)} · {outcome}"
    return Message(
        f"💰 <b>Оплачен заказ #{order.number}</b>{' · DEMO' if order.mode == 'demo' else ''}\n"
        f"{item(order)} · {fmt_money(order.total, order.currency)} · {escape(order.payment_provider)}\n"
        f"Покупатель: {who}{lucky}",
        None,
    )


def admin_attention(order: Order, reason: str) -> Message:
    return Message(
        f"🛠 <b>Заказ #{order.number} требует внимания</b>\n{escape(reason)}\n"
        f"{item(order)} → {escape('@' + order.recipient_username) if order.recipient_username else 'себе'}",
        {"inline_keyboard": [[{"text": "Открыть в админке", "url": f"{get_settings().admin_url}orders/{order.id}"}]]},
    )


def admin_new_ticket(ticket_id: int, subject: str, username: str | None) -> Message:
    who = f"@{escape(username)}" if username else "пользователь без username"
    return Message(
        f"🆘 <b>Новое обращение #{ticket_id}</b> от {who}\n{escape(subject)}",
        {"inline_keyboard": [[{"text": "Ответить", "url": f"{get_settings().admin_url}support/{ticket_id}"}]]},
    )
