"""Telegram Stars payments (Lucky Buy): the pre-checkout question and the
successful payment. The payment goes through the same pipeline as provider
webhooks (de-duplication, amount and currency check), see
``payments/telegram_stars.py``."""

from __future__ import annotations

import uuid
from html import escape

from aiogram import F, Router
from aiogram.types import InlineKeyboardMarkup, Message, PreCheckoutQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.enums import PaymentStatus
from ...database.models import Order, Payment, User
from ...payments import service as payments
from ...payments.registry import get_payment_provider
from ...payments.telegram_stars import CURRENCY, TelegramStarsProvider
from ...services.app_settings import RuntimeSettings
from ...services.state_machine import OPEN_STATUSES
from ...shared.timeutil import utcnow
from ..keyboards import back_row, webapp_button

router = Router(name="payments")


async def _payment(session: AsyncSession, payload: str) -> tuple[Payment, Order] | None:
    try:
        payment_id = uuid.UUID(payload)
    except ValueError:
        return None
    row = (
        await session.execute(
            select(Payment, Order)
            .join(Order, Order.id == Payment.order_id)
            .where(Payment.id == payment_id, Payment.provider == "telegram_stars")
        )
    ).one_or_none()
    return (row[0], row[1]) if row else None


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    """Telegram waits up to 10 seconds for this answer before charging."""
    found = await _payment(session, query.invoice_payload)
    error = None
    if found is None:
        error = "Счёт не найден. Оформите заказ заново"
    else:
        payment, order = found
        owner = await session.get(User, order.user_id)
        if query.currency != CURRENCY or query.total_amount != int(payment.amount):
            error = "Сумма счёта изменилась. Оформите заказ заново"
        elif payment.status not in (PaymentStatus.created, PaymentStatus.pending) or order.status not in OPEN_STATUSES:
            error = "Заказ уже оплачен или закрыт"
        elif order.expires_at is not None and order.expires_at <= utcnow():
            error = "Время на оплату истекло. Оформите заказ заново"
        elif owner is None or owner.telegram_id != query.from_user.id:
            error = "Этот счёт выставлен другому пользователю"
    if error:
        await query.answer(ok=False, error_message=error)
    else:
        await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession, runtime: RuntimeSettings) -> None:
    paid = message.successful_payment
    assert paid is not None
    provider = get_payment_provider("telegram_stars")
    assert isinstance(provider, TelegramStarsProvider)
    headers, body = provider.build_event(
        charge_id=paid.telegram_payment_charge_id,
        payload=paid.invoice_payload,
        total_amount=paid.total_amount,
        currency=paid.currency,
        payer_id=message.from_user.id if message.from_user else 0,
    )
    result = await payments.handle_webhook(session, "telegram_stars", headers, body, "telegram", runtime)
    await session.commit()
    found = await _payment(session, paid.invoice_payload)
    if found is None:
        await message.answer("✅ Оплата получена. Если заказ не обновится, напишите в поддержку.")
        return
    _, order = found
    text = f"✅ Оплата получена, заказ <b>#{escape(order.number)}</b> обновлён."
    if result.get("result") == "duplicate_refund":
        text = f"↩️ Заказ <b>#{escape(order.number)}</b> уже был оплачен — повторная оплата будет возвращена."
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[webapp_button("📦 Открыть заказ", f"orders/{order.id}", style="primary")], back_row()]
        ),
    )
