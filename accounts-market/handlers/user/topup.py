"""Balance top-up: amount choice, invoice, server-side status check."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import media
from bot.callbacks import Nav, Pay, Payments, Topup
from bot.ui import Screen, show
from database.models import Payment, PaymentStatus, User
from keyboards import user as kb
from payments.service import PaymentService
from services.errors import ShopError
from services.formatting import dt, money, parse_rubles
from services.shop_settings import ShopSettings

router = Router(name="topup")

PRESETS = (100, 300, 500, 1000, 2500, 5000)
PAY_PAGE = 8

STATUS = {
    PaymentStatus.PENDING: "⏳ ожидает оплаты",
    PaymentStatus.PAID: "✅ зачислено",
    PaymentStatus.EXPIRED: "⌛ истёк",
    PaymentStatus.FAILED: "⚠️ ошибка",
    PaymentStatus.REFUNDED: "↩️ возвращён",
}


class TopupForm(StatesGroup):
    amount = State()


def presets_for(shop: ShopSettings, payments: PaymentService) -> list[int]:
    allowed = [p for p in PRESETS if shop.min_topup <= p * 100 <= payments.max_amount]
    return allowed or [shop.min_topup // 100]


async def topup_screen(user: User, shop: ShopSettings, payments: PaymentService) -> Screen:
    text = (
        "💎 <b>Пополнение баланса</b>\n\n"
        f"💰 Текущий баланс: <b>{money(user.balance)}</b>\n"
        f"Способ оплаты: {payments.provider.title}\n"
        f"Минимальная сумма: {money(shop.min_topup)}\n\n"
        "Выберите сумму. Деньги зачисляются автоматически после подтверждения платёжной системой."
    )
    if payments.provider.is_demo:
        text += "\n\n🧪 <b>DEMO-режим</b>: настоящие деньги не списываются."
    return Screen(text, kb.topup(presets_for(shop, payments)), await media.banner("topup", shop.shop_name))


@router.callback_query(Nav.filter(F.to == "topup"))
async def topup(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, shop: ShopSettings, payments: PaymentService
) -> None:
    await state.clear()
    await session.refresh(user)
    await show(callback, await topup_screen(user, shop, payments))


@router.message(Command("topup"))
async def topup_command(message: Message, state: FSMContext, user: User, shop: ShopSettings, payments: PaymentService) -> None:
    await state.clear()
    await show(message, await topup_screen(user, shop, payments))


def payment_text(p: Payment, demo: bool) -> str:
    lines = [
        "🧾 <b>Счёт на пополнение</b>",
        "",
        f"Номер: <code>{p.uid}</code>",
        f"Сумма: <b>{money(p.amount)}</b>",
        f"Статус: {STATUS.get(p.status, p.status)}",
    ]
    if p.status == PaymentStatus.PENDING:
        lines.append(f"Действует до: {dt(p.expires_at)}")
        lines.append("")
        if demo:
            lines.append("🧪 DEMO-режим: нажмите «Провести оплату», чтобы имитировать подтверждение от провайдера.")
        else:
            lines.append("1. Нажмите «Оплатить» и завершите оплату.")
            lines.append("2. Баланс пополнится автоматически, обычно за минуту.")
            lines.append("Если уведомление не пришло, нажмите «Проверить оплату».")
    elif p.status == PaymentStatus.PAID:
        lines += ["", "Средства зачислены на баланс."]
    return "\n".join(lines)


async def payment_screen(p: Payment, shop: ShopSettings, payments: PaymentService) -> Screen:
    banner = "paid" if p.status == PaymentStatus.PAID else "payment"
    return Screen(payment_text(p, payments.provider.is_demo), kb.payment(p, payments.provider.is_demo), await media.banner(banner, shop.shop_name))


async def create_payment(
    event: Message | CallbackQuery, amount: int, user: User, shop: ShopSettings, payments: PaymentService
) -> None:
    try:
        p = await payments.create(user.id, amount, shop.min_topup, shop.shop_name)
    except ShopError as exc:
        screen = Screen(
            f"⚠️ <b>Не удалось создать счёт</b>\n\n{exc.message}",
            kb.rows([kb.btn("◀️ Пополнение", Nav(to="topup")), kb.HOME]),
            await media.banner("error", shop.shop_name),
        )
        await show(event, screen)
        return
    await show(event, await payment_screen(p, shop, payments))


@router.callback_query(Topup.filter(F.amount > 0))
async def preset(
    callback: CallbackQuery, callback_data: Topup, user: User, shop: ShopSettings, payments: PaymentService
) -> None:
    await create_payment(callback, callback_data.amount * 100, user, shop, payments)


@router.callback_query(Topup.filter(F.amount == 0))
async def custom_amount(callback: CallbackQuery, state: FSMContext, shop: ShopSettings, payments: PaymentService) -> None:
    await state.set_state(TopupForm.amount)
    text = (
        "✍️ <b>Своя сумма</b>\n\n"
        f"Отправьте сумму пополнения в рублях, от {money(shop.min_topup)} до {money(payments.max_amount)}.\n"
        "Например: <code>750</code>"
    )
    await show(callback, Screen(text, kb.cancel_input(Nav(to="topup")), await media.banner("topup", shop.shop_name)))


@router.message(TopupForm.amount, F.text)
async def custom_amount_value(
    message: Message, state: FSMContext, user: User, shop: ShopSettings, payments: PaymentService
) -> None:
    amount = parse_rubles(message.text or "")
    if amount is None or amount < shop.min_topup or amount > payments.max_amount:
        await message.answer(
            f"⚠️ Укажите сумму от {money(shop.min_topup)} до {money(payments.max_amount)}, например <code>750</code>.",
            reply_markup=kb.cancel_input(Nav(to="topup")),
        )
        return
    await state.clear()
    await create_payment(message, amount, user, shop, payments)


@router.message(TopupForm.amount)
async def custom_amount_wrong(message: Message) -> None:
    await message.answer("Отправьте сумму числом, например <code>750</code>.", reply_markup=kb.cancel_input(Nav(to="topup")))


async def _own_payment(session: AsyncSession, payment_id: int, user: User) -> Payment | None:
    p = await session.get(Payment, payment_id, populate_existing=True)
    return p if p is not None and p.user_id == user.id else None


@router.callback_query(Pay.filter())
async def payment_action(
    callback: CallbackQuery,
    callback_data: Pay,
    session: AsyncSession,
    user: User,
    shop: ShopSettings,
    payments: PaymentService,
    callback_answer: CallbackAnswer,
) -> None:
    p = await _own_payment(session, callback_data.id, user)
    if p is None:
        callback_answer.text, callback_answer.show_alert = "Счёт не найден", True
        return
    if callback_data.action in ("check", "demo") and p.status == PaymentStatus.PENDING:
        try:
            if callback_data.action == "demo":
                result = await payments.demo_confirm(p.id, user.id)
            else:
                result = await payments.check(p.id)
        except ShopError as exc:
            callback_answer.text, callback_answer.show_alert = exc.message, True
            return
        p = result.payment
        if p.status == PaymentStatus.PENDING:
            callback_answer.text = "Оплата пока не поступила. Если вы уже оплатили, подождите минуту."
            callback_answer.show_alert = True
        elif p.status == PaymentStatus.PAID:
            callback_answer.text = "✅ Баланс пополнен"
    await show(callback, await payment_screen(p, shop, payments))


@router.callback_query(Payments.filter())
async def payments_history(
    callback: CallbackQuery, callback_data: Payments, session: AsyncSession, user: User, shop: ShopSettings
) -> None:
    page = max(callback_data.page, 0)
    total = await session.scalar(select(func.count(Payment.id)).where(Payment.user_id == user.id)) or 0
    items = list(
        (
            await session.execute(
                select(Payment)
                .where(Payment.user_id == user.id)
                .order_by(Payment.id.desc())
                .limit(PAY_PAGE)
                .offset(page * PAY_PAGE)
            )
        ).scalars()
    )
    lines = ["🧾 <b>История пополнений</b>", ""]
    for p in items:
        lines.append(f"{STATUS.get(p.status, p.status)} · <b>{money(p.amount)}</b>\n<i>{dt(p.created_at)} · {p.uid}</i>")
    if not items:
        lines.append("Пополнений пока не было.")
    pages = max(1, math.ceil(total / PAY_PAGE))
    await show(callback, Screen("\n".join(lines), kb.payments_list(items, page, pages)))
