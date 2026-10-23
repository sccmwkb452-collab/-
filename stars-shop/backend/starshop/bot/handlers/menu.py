from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...database.models import Order, User
from ...notifications.templates import STATUS_LABELS, fmt_money, fmt_stars
from ...payments.registry import enabled_providers
from ...services.app_settings import RuntimeSettings
from ...services.users import referral_link, user_stats
from ...shared.timeutil import fmt_local
from ..keyboards import main_menu, webapp_button, with_back

router = Router(name="menu")

STATUS_ICON = {
    "created": "🕓",
    "pending_payment": "💳",
    "paid": "✅",
    "processing": "⚙️",
    "completed": "🌟",
    "failed": "⚠️",
    "refund_pending": "↩️",
    "refunded": "💸",
    "cancelled": "✖️",
    "lost": "🎲",
}


def welcome_text(runtime: RuntimeSettings, user: User) -> str:
    name = escape(user.first_name or "друг")
    demo = "\n\n🧪 <i>Магазин работает в DEMO-режиме: оплата и доставка тестовые.</i>" if runtime.shop.mode == "demo" else ""
    return (
        f"✨ <b>{escape(runtime.brand.name)}</b> · {escape(runtime.brand.tagline)}\n\n"
        f"Привет, {name}! Здесь можно купить Telegram Stars для себя или в подарок другу.\n"
        "Выберите пакет, оплатите удобным способом и следите за статусом заказа прямо в Telegram."
        f"{demo}"
    )


async def _show(target: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    if isinstance(target, CallbackQuery):
        await target.answer()
        if target.message is not None:
            try:
                await target.message.edit_text(text, reply_markup=markup)
                return
            except TelegramBadRequest:
                pass  # message too old or unchanged: send a new one
            await target.message.answer(text, reply_markup=markup)
        return
    await target.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def start(
    message: Message, command: CommandObject, state: FSMContext, db_user: User, runtime: RuntimeSettings, session: AsyncSession
) -> None:
    await state.clear()
    payload = (command.args or "").strip()
    if payload.startswith("order_"):
        number = payload.removeprefix("order_").upper()[:16]
        order = (await session.execute(select(Order).where(Order.number == number, Order.user_id == db_user.id))).scalar_one_or_none()
        if order is not None:
            await message.answer(
                f"{STATUS_ICON.get(order.status, '•')} Заказ <b>#{order.number}</b>: {STATUS_LABELS.get(order.status, order.status)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[webapp_button("Посмотреть заказ", f"orders/{order.id}")]]),
            )
            return
    await message.answer(welcome_text(runtime, db_user), reply_markup=main_menu(lucky=runtime.lucky_available))


@router.message(Command("menu"))
async def menu_cmd(message: Message, db_user: User, runtime: RuntimeSettings) -> None:
    await message.answer(welcome_text(runtime, db_user), reply_markup=main_menu(lucky=runtime.lucky_available))


@router.callback_query(F.data == "menu:home")
async def home(callback: CallbackQuery, db_user: User, runtime: RuntimeSettings) -> None:
    await _show(callback, welcome_text(runtime, db_user), main_menu(lucky=runtime.lucky_available))


@router.callback_query(F.data == "nohttps")
async def no_https(callback: CallbackQuery) -> None:
    await callback.answer("Mini App откроется после настройки HTTPS-домена (PUBLIC_BASE_URL)", show_alert=True)


async def profile_view(session: AsyncSession, user: User, runtime: RuntimeSettings) -> tuple[str, InlineKeyboardMarkup]:
    stats = await user_stats(session, user)
    tz = get_settings().display_timezone
    currency = get_settings().shop_currency
    last = "—"
    if stats.last_order is not None:
        o = stats.last_order
        last = f"#{o.number} · {fmt_stars(o.stars_amount)} ⭐️ · {STATUS_LABELS.get(o.status, o.status)}"
    lines = [
        "👤 <b>Мой профиль</b>",
        "",
        f"Telegram ID: <code>{user.telegram_id}</code>",
        f"С нами с: {fmt_local(user.first_seen_at, tz, '%d.%m.%Y')}",
        f"Заказов: <b>{stats.orders_count}</b> (выполнено {stats.completed_count})",
        f"Сумма покупок: <b>{fmt_money(stats.total_spent, currency)}</b>",
        f"Последний заказ: {last}",
    ]
    if runtime.referral.enabled:
        lines.append(f"Реферальный код: <code>{user.referral_code}</code>")
    if user.is_blocked:
        lines += ["", "⛔️ Покупки для аккаунта ограничены. Напишите в поддержку."]
    return "\n".join(lines), with_back([webapp_button("🧾 История заказов", "orders")])


@router.callback_query(F.data == "menu:profile")
async def profile(callback: CallbackQuery, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    text, markup = await profile_view(session, db_user, runtime)
    await _show(callback, text, markup)


@router.message(Command("profile"))
async def profile_cmd(message: Message, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    text, markup = await profile_view(session, db_user, runtime)
    await message.answer(text, reply_markup=markup)


async def orders_view(session: AsyncSession, user: User) -> tuple[str, InlineKeyboardMarkup]:
    rows = (await session.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(5))).scalars().all()
    tz = get_settings().display_timezone
    if not rows:
        return "🧾 <b>Мои заказы</b>\n\nЗаказов пока нет — самое время выбрать первый пакет ✨", with_back(
            [webapp_button("✨ Купить Stars", "catalog")]
        )
    lines = ["🧾 <b>Последние заказы</b>", ""]
    for o in rows:
        lines.append(
            f"{STATUS_ICON.get(o.status, '•')} <b>#{o.number}</b> · {fmt_stars(o.stars_amount)} ⭐️ · {fmt_money(o.total, o.currency)}\n"
            f"    {STATUS_LABELS.get(o.status, o.status)} · {fmt_local(o.created_at, tz)}"
        )
    return "\n".join(lines), with_back([webapp_button("Все заказы", "orders")])


@router.callback_query(F.data == "menu:orders")
async def orders(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    text, markup = await orders_view(session, db_user)
    await _show(callback, text, markup)


@router.message(Command("orders"))
async def orders_cmd(message: Message, session: AsyncSession, db_user: User) -> None:
    text, markup = await orders_view(session, db_user)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "menu:payments")
async def payments(callback: CallbackQuery, runtime: RuntimeSettings) -> None:
    providers = enabled_providers(runtime.shop.mode)
    fees = runtime.checkout.provider_fee_percent
    lines = ["💳 <b>Способы оплаты</b>", ""]
    if not providers:
        lines.append("Оплата временно недоступна.")
    for p in providers:
        fee = fees.get(p.name)
        fee_text = f" · комиссия {fee}%" if fee and fee > 0 else ""
        lines.append(f"• <b>{escape(p.title)}</b>{fee_text}\n  {escape(p.description)}")
    lines += [
        "",
        "Заказ уходит в работу только после того, как платёжный провайдер подтвердит оплату нашему серверу.",
        "",
        f"↩️ <b>Возвраты.</b> {escape(runtime.content.legal.refund_policy)}",
    ]
    await _show(callback, "\n".join(lines), with_back([webapp_button("📄 Условия покупки", "info/terms")]))


@router.callback_query(F.data == "menu:bonus")
async def bonus(callback: CallbackQuery, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    cfg = runtime.referral
    if not cfg.enabled:
        await _show(callback, "🎁 <b>Бонусы</b>\n\nБонусная программа сейчас не активна. Мы сообщим, когда она запустится.", with_back())
        return
    stats = await user_stats(session, db_user)
    currency = get_settings().shop_currency
    reward = f"{cfg.reward_value}% от суммы его первого заказа" if cfg.reward_kind == "percent" else fmt_money(cfg.reward_value, currency)
    link = referral_link(db_user)
    lines = [
        "🎁 <b>Бонусы</b>",
        "",
        f"Баланс: <b>{fmt_money(db_user.bonus_balance, currency)}</b>",
        f"Приглашено: {stats.invited_count} · с бонусом: {stats.rewarded_count}",
        "",
        f"Пригласите друга по ссылке — когда его первый заказ будет оплачен и выполнен, вы получите {reward} на бонусный баланс.",
        f"Бонусами можно оплатить до {cfg.max_bonus_spend_percent}% следующих заказов.",
    ]
    if link:
        lines += ["", f"Ваша ссылка:\n<code>{escape(link)}</code>"]
    await _show(callback, "\n".join(lines), with_back())


@router.message()
async def fallback(message: Message, db_user: User, runtime: RuntimeSettings) -> None:
    await message.answer(welcome_text(runtime, db_user), reply_markup=main_menu(lucky=runtime.lucky_available))
