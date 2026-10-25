"""Admin: payments, status checks, refunds and processing errors."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.states import PaymentAdmin
from bot.callbacks import Adm
from bot.ui import Screen, show
from database.models import Payment, PaymentStatus
from handlers.user.topup import STATUS
from keyboards import admin as akb
from keyboards.user import btn, rows
from payments.service import PaymentService
from services.errors import ShopError
from services.formatting import dt, esc, money

router = Router(name="admin_payments")
PAGE = 8

FILTERS = {
    "": ("💳 Все платежи", None),
    "p": ("⏳ Ожидают оплаты", Payment.status == PaymentStatus.PENDING),
    "ok": ("✅ Оплаченные", Payment.status == PaymentStatus.PAID),
    "e": ("⚠️ Ошибки обработки", Payment.last_error.is_not(None) | (Payment.status == PaymentStatus.FAILED)),
    "r": ("↩️ Возвраты", Payment.status == PaymentStatus.REFUNDED),
}


@router.callback_query(Adm.filter(F.s == "pays"))
async def payments_list(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    key = callback_data.v if callback_data.v in FILTERS else ""
    title, cond = FILTERS[key]
    base = select(Payment)
    if cond is not None:
        base = base.where(cond)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    pages = max(1, math.ceil(total / PAGE))
    page = min(max(callback_data.p, 0), pages - 1)
    items = (await session.execute(base.order_by(Payment.id.desc()).limit(PAGE).offset(page * PAGE))).scalars()
    buttons = [
        (f"{STATUS.get(p.status, p.status).split()[0]} {money(p.amount)} · {p.uid} · {p.user_id}", Adm(s="pay", id=p.id, v=key))
        for p in items
    ]
    filters = [btn(label.split()[0], Adm(s="pays", v=k)) for k, (label, _) in FILTERS.items() if k != key]
    await show(
        callback,
        Screen(
            f"<b>{title}</b>\n\nВсего: {total}\nФильтры: 💳 все · ⏳ ожидают · ✅ оплачены · ⚠️ ошибки · ↩️ возвраты",
            akb.listing(buttons, page, pages, lambda n: Adm(s="pays", p=n, v=key), [filters]),
        ),
    )


def payment_screen(p: Payment, provider_name: str, v: str = "") -> Screen:
    lines = [
        f"💳 <b>Платёж {p.uid}</b> · #{p.id}",
        "",
        f"Пользователь: <code>{p.user_id}</code>",
        f"Сумма: <b>{money(p.amount)}</b>",
        f"Провайдер: {p.provider} · счёт: <code>{esc(p.external_id or '—')}</code>",
        f"Статус: {STATUS.get(p.status, p.status)}",
        f"Создан: {dt(p.created_at)}",
        f"Истекает: {dt(p.expires_at)}",
        f"Оплачен: {dt(p.paid_at)}",
        f"Последняя проверка: {dt(p.checked_at)}",
    ]
    if p.refunded_at:
        lines.append(f"Возврат: {dt(p.refunded_at)}")
    if p.last_error:
        lines.append(f"\n⚠️ Ошибка: <code>{esc(p.last_error)}</code>")
    kb = []
    if p.status in (PaymentStatus.PENDING, PaymentStatus.EXPIRED) and p.provider == provider_name:
        kb.append([btn("🔄 Проверить статус у провайдера", Adm(s="paycheck", id=p.id), style="primary")])
    if p.status == PaymentStatus.PAID:
        kb.append([btn("↩️ Оформить возврат", Adm(s="payref", id=p.id), style="danger")])
    kb.append([btn("👤 Пользователь", Adm(s="usr", id=p.user_id))])
    kb.append([akb.back("pays", "◀️ К платежам", v=v)])
    return Screen("\n".join(lines), rows(*kb))


@router.callback_query(Adm.filter(F.s == "pay"))
async def payment_card(
    callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext, payments: PaymentService, callback_answer: CallbackAnswer
) -> None:
    await state.clear()
    p = await session.get(Payment, callback_data.id, populate_existing=True)
    if p is None:
        callback_answer.text = "Платёж не найден"
        return
    await show(callback, payment_screen(p, payments.provider.name, callback_data.v))


@router.callback_query(Adm.filter(F.s == "paycheck"))
async def payment_check(callback: CallbackQuery, callback_data: Adm, payments: PaymentService, callback_answer: CallbackAnswer) -> None:
    try:
        result = await payments.check(callback_data.id)
    except ShopError as exc:
        callback_answer.text, callback_answer.show_alert = exc.message, True
        return
    callback_answer.text = "Зачислено" if result.credited else f"Статус: {STATUS.get(result.payment.status, result.payment.status)}"
    await show(callback, payment_screen(result.payment, payments.provider.name))


@router.callback_query(Adm.filter(F.s == "payref"))
async def refund_prompt(callback: CallbackQuery, callback_data: Adm, state: FSMContext, payments: PaymentService) -> None:
    await state.set_state(PaymentAdmin.refund_reason)
    await state.update_data(pid=callback_data.id)
    how = (
        "Деньги будут возвращены через API провайдера."
        if payments.provider.supports_refund
        else f"{payments.provider.title} не поддерживает возврат через API: после подтверждения верните деньги вручную в кабинете провайдера."
    )
    text = (
        "↩️ <b>Возврат пополнения</b>\n\n"
        f"Сумма платежа будет списана с баланса пользователя. {how}\n\n"
        "Отправьте причину возврата:"
    )
    await show(callback, Screen(text, akb.cancel("pay", id=callback_data.id)))


@router.message(PaymentAdmin.refund_reason, F.text)
async def refund_reason(message: Message, state: FSMContext) -> None:
    pid = (await state.get_data())["pid"]
    reason = message.text.strip()
    if not 3 <= len(reason) <= 256:
        await message.answer("Причина: от 3 до 256 символов.", reply_markup=akb.cancel("pay", id=pid))
        return
    await state.update_data(reason=reason)
    await message.answer(
        f"Подтвердите возврат платежа #{pid}.\nПричина: {esc(reason)}",
        reply_markup=akb.confirm(Adm(s="payrefok", id=pid), Adm(s="pay", id=pid), "↩️ Вернуть"),
    )


@router.callback_query(Adm.filter(F.s == "payrefok"))
async def refund(
    callback: CallbackQuery, callback_data: Adm, state: FSMContext, payments: PaymentService, callback_answer: CallbackAnswer
) -> None:
    data = await state.get_data()
    if data.get("pid") != callback_data.id or not data.get("reason"):
        callback_answer.text, callback_answer.show_alert = "Сначала укажите причину", True
        return
    await state.clear()
    try:
        p = await payments.refund(callback_data.id, callback.from_user.id, data["reason"])
    except ShopError as exc:
        callback_answer.text, callback_answer.show_alert = exc.message, True
        return
    callback_answer.text = "Возврат оформлен"
    try:
        await callback.bot.send_message(
            p.user_id, f"↩️ Пополнение {p.uid} на {money(p.amount)} возвращено.\nПричина: {esc(data['reason'])}"
        )
    except TelegramAPIError:
        pass
    await show(callback, payment_screen(p, payments.provider.name))
