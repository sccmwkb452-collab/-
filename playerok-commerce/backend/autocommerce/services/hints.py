"""Operator-assist messages.

When an automation cannot act on PlayerOK (no API), the system sends the
operator a ready-to-use text with a copy button instead, and logs it as
SUGGESTED — never as if it had been sent to the buyer.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import LogResult, Severity
from ..database.models import Order
from ..integrations.marketplace.playerok_manual import get_marketplace
from ..shared.money import fmt_money
from . import app_settings
from . import templates as tpl
from .audit import automation_log
from .autosettings import feature, is_active
from .notifications import Button, btn, esc, notify

STATUS_NEXT_STEPS: dict[str, str] = {
    "new": "Заказ принят, начинаем обработку.",
    "pending_review": "Проверяем детали заказа.",
    "pending_purchase": "Готовим товар к выдаче.",
    "pending_confirmation": "Готовим товар к выдаче.",
    "processing": "Заказ выполняется.",
    "ready_for_delivery": "Товар готов, скоро передадим.",
    "delivered": "Товар передан — проверьте и подтвердите получение.",
    "completed": "Сделка завершена.",
    "error": "Разбираемся с задержкой и сообщим результат.",
    "refund": "Оформляется возврат.",
    "dispute": "Разбираемся с вопросом по заказу.",
    "cancelled": "Заказ отменён.",
}


async def order_context(session: AsyncSession, order: Order | None, **extra: Any) -> dict[str, Any]:
    from ..database.enums import ORDER_STATUS_LABELS

    shop = (await app_settings.get_setting(session, "shop.profile"))["name"]
    ctx: dict[str, Any] = {"shop": shop}
    if order is not None:
        item = order.items[0] if order.items else None
        product = item.product if item else None
        ctx.update(
            buyer=order.buyer_name or "покупатель",
            order_number=order.number,
            status=ORDER_STATUS_LABELS.get(order.status, order.status.value),
            next_steps=STATUS_NEXT_STEPS.get(order.status.value, ""),
            price=fmt_money(order.total_amount),
            quantity=str(sum(i.quantity for i in order.items)),
        )
        if product is not None:
            ctx.update(
                product=product.name,
                delivery_time=product.delivery_time,
                instructions=product.buyer_instructions or product.activation_notes or "",
                region=product.region or "без ограничений",
            )
    ctx.update({k: v for k, v in extra.items() if v is not None})
    return ctx


def copy_buttons(text: str) -> list[list[Button]]:
    # Telegram limits copy_text to 256 characters; longer texts are shown as <code> (tap to copy).
    return [[btn("📋 Скопировать текст", copy=text)]] if len(text) <= 256 else []


async def suggest(
    session: AsyncSession,
    feature_code: str,
    field: str,
    order: Order | None,
    *,
    title: str,
    extra_buttons: list[list[Button]] | None = None,
    context: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    respect_toggle: bool = True,
) -> str | None:
    """Render the feature's text and send it to the operator (or to the buyer
    when the marketplace supports it). Returns the text or None when the
    feature is off."""
    active, cfg = await is_active(session, feature_code)
    if respect_toggle and not active:
        return None
    f = feature(feature_code)
    text = tpl.render(str(cfg.get(field, "")), await order_context(session, order, **(context or {})))
    if not text:
        return None
    market = get_marketplace()
    order_id = order.id if order is not None else None
    if all(market.supports(c) for c in f.requires):
        # an official integration would send here; the manual adapter never reaches this branch
        await automation_log(session, feature_code, "send", LogResult.OK, text, order_id=order_id)
        return text
    buttons = copy_buttons(text) + (extra_buttons or [])
    if order is not None:
        buttons.append([btn("🛒 Открыть заказ", f"ord:open:{order.id}")])
    body = f"{esc(title)}\n\nТекст для покупателя{f' ({esc(order.buyer_name)})' if order and order.buyer_name else ''}:\n<code>{esc(text)}</code>"
    body += "\n\n<i>PlayerOK без API: отправьте сообщение в чате сделки вручную.</i>"
    await notify(
        session,
        "operator_hint",
        f"{f.emoji} {f.title}",
        body,
        severity=Severity.INFO,
        buttons=buttons,
        entity_type="order" if order else None,
        entity_id=order_id,
        dedupe_key=dedupe_key,
        permission="messages.manage",
    )
    await automation_log(session, feature_code, "suggest", LogResult.SUGGESTED, text, order_id=order_id)
    return text
