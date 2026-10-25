"""Admin home and statistics."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from admin import stats as stats_service
from bot.callbacks import Adm
from bot.ui import Screen, show
from keyboards import admin as akb
from keyboards.user import btn, rows
from payments.service import PaymentService
from services.formatting import esc, money
from services.shop_settings import ShopSettings

router = Router(name="admin_panel")


def home_screen(shop: ShopSettings, payments: PaymentService) -> Screen:
    mode = "🧪 DEMO" if payments.provider.is_demo else f"✅ {payments.provider.title}"
    text = (
        f"🛠 <b>Админ-панель · {esc(shop.shop_name)}</b>\n\n"
        f"Платежи: {mode}\n\n"
        "Выберите раздел. Все действия с деньгами записываются в журнал."
    )
    return Screen(text, akb.menu())


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext, shop: ShopSettings, payments: PaymentService) -> None:
    await state.clear()
    await show(message, home_screen(shop, payments))


@router.callback_query(Adm.filter(F.s == "home"))
async def admin_home(callback: CallbackQuery, state: FSMContext, shop: ShopSettings, payments: PaymentService) -> None:
    await state.clear()
    await show(callback, home_screen(shop, payments))


@router.callback_query(Adm.filter(F.s == "stats"))
async def stats(callback: CallbackQuery, session: AsyncSession) -> None:
    s = await stats_service.collect(session)
    top = "\n".join(
        f"{i}. {esc(title)} — {sold} шт. · {money(revenue)}" for i, (title, sold, revenue) in enumerate(s.top, start=1)
    ) or "Продаж пока нет"
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 <b>Пользователи:</b> {s.users}\n"
        f"   за 24 часа: +{s.users_today} · за 7 дней: +{s.users_week}\n"
        f"   покупателей: {s.buyers}\n\n"
        f"🛒 <b>Заказы:</b> {s.orders} (за 24 часа: {s.orders_today})\n"
        f"💵 <b>Выручка:</b> {money(s.revenue)} (за 24 часа: {money(s.revenue_today)})\n\n"
        f"💎 <b>Пополнения:</b> {s.topups} на {money(s.topups_sum)}\n"
        f"   ожидают оплаты: {s.pending_payments}\n"
        f"↩️ <b>Возвраты:</b> заказов {s.refunds} на {money(s.refunds_sum)} · пополнений {s.payment_refunds}\n"
        f"💰 Сумма балансов пользователей: {money(s.balances)}\n\n"
        f"🔥 <b>Популярные товары</b>\n{top}"
    )
    await show(callback, Screen(text, rows([btn("🔄 Обновить", Adm(s="stats"))], [akb.ADMIN_HOME])))
