from __future__ import annotations

from html import escape
from urllib.parse import quote

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...database.enums import BotButtonAction, ProductKind
from ...database.models import BotButton, Order, Product, User
from ...notifications.templates import STATUS_LABELS, fmt_money, fmt_stars
from ...services import bot_buttons, referrals
from ...services.app_settings import RuntimeSettings
from ...services.users import referral_link, user_stats
from ...shared.items import item_title
from ...shared.timeutil import fmt_local
from ..emoji import em
from ..keyboards import button, main_menu, webapp_button, with_back

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
        f"{em(runtime, 'welcome')} <b>{escape(runtime.brand.name)}</b> · {escape(runtime.brand.tagline)}\n\n"
        f"Привет, {name}! Здесь можно купить Telegram Stars и Telegram Premium себе или в подарок другу.\n\n"
        f"{em(runtime, 'shop')} <b>Открыть магазин</b> — витрина, Lucky Buy и история заказов.\n"
        f"{em(runtime, 'stars')} <b>Купить Stars</b> и {em(runtime, 'premium')} <b>Premium</b> — прямо в этом чате."
        f"{demo}"
    )


async def menu_markup(session: AsyncSession, runtime: RuntimeSettings | None = None) -> InlineKeyboardMarkup:
    premium = await session.scalar(
        select(Product.id).where(Product.kind == ProductKind.premium, Product.is_active.is_(True), Product.is_archived.is_(False)).limit(1)
    )
    return main_menu(await bot_buttons.active_buttons(session), runtime=runtime, premium=premium is not None)


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
    await message.answer(welcome_text(runtime, db_user), reply_markup=await menu_markup(session, runtime))


@router.message(Command("menu"))
async def menu_cmd(message: Message, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    await message.answer(welcome_text(runtime, db_user), reply_markup=await menu_markup(session, runtime))


@router.callback_query(F.data == "menu:home")
async def home(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    await state.clear()
    await _show(callback, welcome_text(runtime, db_user), await menu_markup(session, runtime))


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
        last = f"#{o.number} · {item_title(o.stars_amount, o.premium_months)} · {STATUS_LABELS.get(o.status, o.status)}"
    lines = [
        "👤 <b>Мой профиль</b>",
        "",
        f"Telegram ID: <code>{user.telegram_id}</code>",
        f"С нами с: {fmt_local(user.first_seen_at, tz, '%d.%m.%Y')}",
        f"Заказов: <b>{stats.orders_count}</b> (выполнено {stats.completed_count})",
        f"Сумма покупок: <b>{fmt_money(stats.total_spent, currency)}</b>",
        f"Бонусный баланс: <b>{fmt_money(user.bonus_balance, currency)}</b>",
        f"Последний заказ: {last}",
    ]
    if user.is_blocked:
        lines += ["", "⛔️ Покупки для аккаунта ограничены. Напишите в поддержку."]
    return "\n".join(lines), with_back(
        [button("🧾 Мои заказы", callback="menu:orders"), button("🎁 Рефералы", callback="menu:referrals")],
        [webapp_button("🌐 Профиль в магазине", "profile", style="primary")],
    )


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
            [button("⭐️ Купить Stars", callback="buy:start", style="success")]
        )
    lines = ["🧾 <b>Последние заказы</b>", ""]
    for o in rows:
        lines.append(
            f"{STATUS_ICON.get(o.status, '•')} <b>#{o.number}</b> · {item_title(o.stars_amount, o.premium_months)} · {fmt_money(o.total, o.currency)}\n"
            f"    {STATUS_LABELS.get(o.status, o.status)} · {fmt_local(o.created_at, tz)}"
        )
    return "\n".join(lines), with_back(
        [button("⭐️ Купить ещё", callback="buy:start", style="success")], [webapp_button("🌐 Все заказы", "orders", style="primary")]
    )


@router.callback_query(F.data == "menu:orders")
async def orders(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    text, markup = await orders_view(session, db_user)
    await _show(callback, text, markup)


@router.message(Command("orders"))
async def orders_cmd(message: Message, session: AsyncSession, db_user: User) -> None:
    text, markup = await orders_view(session, db_user)
    await message.answer(text, reply_markup=markup)


async def referrals_view(session: AsyncSession, user: User, runtime: RuntimeSettings) -> tuple[str, InlineKeyboardMarkup]:
    cfg = runtime.referral
    if not cfg.enabled:
        return "🎁 <b>Реферальная программа</b>\n\nПрограмма сейчас не активна. Мы сообщим, когда она запустится.", with_back()
    currency = get_settings().shop_currency
    data = await referrals.overview(session, user, limit=5)
    reward = f"{cfg.reward_value}% от суммы его заказа" if cfg.reward_kind == "percent" else fmt_money(cfg.reward_value, currency)
    condition = "первый выполненный заказ"
    if cfg.min_order_amount > 0:
        condition += f" от {fmt_money(cfg.min_order_amount, currency)}"
    link = referral_link(user)
    lines = [
        "🎁 <b>Реферальная программа</b>",
        "",
        f"Приглашено: <b>{data.invited}</b> · активировано: <b>{data.activated}</b>",
        f"Заработано: <b>{fmt_money(data.earned, currency)}</b> · баланс: <b>{fmt_money(user.bonus_balance, currency)}</b>",
        "",
        f"За каждого друга вы получаете {reward}. Условие — {condition} друга, оплаченный и выполненный.",
        f"Бонусами можно оплатить до {cfg.max_bonus_spend_percent}% своих заказов.",
    ]
    if runtime.shop.mode == "demo":
        lines.append("<i>В DEMO-режиме бонусы не начисляются: только за реальные оплаченные заказы.</i>")
    if data.history:
        lines += ["", "<b>Последние начисления</b>"]
        tz = get_settings().display_timezone
        for t in data.history:
            sign = "+" if t.amount > 0 else "−"
            lines.append(
                f"{sign}{fmt_money(abs(t.amount), currency)} · {escape(t.comment or t.kind)} · {fmt_local(t.created_at, tz, '%d.%m')}"
            )
    rows = []
    if link:
        lines += ["", f"Ваша ссылка:\n<code>{escape(link)}</code>"]
        share = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote('Покупаю Telegram Stars здесь — попробуй!', safe='')}"
        rows.append([button("📤 Поделиться ссылкой", url=share, style="primary")])
    rows.append([webapp_button("🌐 Подробнее в магазине", "referrals")])
    return "\n".join(lines), with_back(*rows)


@router.callback_query(F.data == "menu:referrals")
async def referrals_screen(callback: CallbackQuery, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    text, markup = await referrals_view(session, db_user, runtime)
    await _show(callback, text, markup)


@router.message(Command("ref"))
async def referrals_cmd(message: Message, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    text, markup = await referrals_view(session, db_user, runtime)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("cb:"))
async def custom_button(callback: CallbackQuery, session: AsyncSession, runtime: RuntimeSettings) -> None:
    """Buttons from Admin → Кнопки бота that send a message or show a package."""
    try:
        button_id = int((callback.data or "").removeprefix("cb:"))
    except ValueError:
        button_id = 0
    b = await session.get(BotButton, button_id)
    if b is None or not b.is_active:
        await callback.answer("Эта кнопка больше не работает", show_alert=True)
        return
    if b.action == BotButtonAction.product and b.product_id:
        product = await session.get(Product, b.product_id)
        if product is None or not product.is_active or product.is_archived:
            await callback.answer("Пакет сейчас недоступен", show_alert=True)
            return
        currency = get_settings().shop_currency
        if product.premium_months:
            head = f"💎 <b>{item_title(0, product.premium_months)}</b> — {fmt_money(product.price, currency)}"
            buy = button("💎 Купить Premium", callback=f"buy:pkg:{product.id}", style="success")
        elif product.stars_amount:
            head = f"⭐️ <b>{fmt_stars(product.stars_amount)} Stars</b> — {fmt_money(product.price, currency)}"
            buy = button("⭐️ Купить этот пакет", callback=f"buy:pkg:{product.id}", style="success")
        else:
            head = f"⭐️ <b>{escape(product.title or 'Своё количество')}</b> — {fmt_money(product.price_per_star, currency)} за звезду"
            buy = button("✏️ Указать количество", callback="buy:custom", style="success")
        text = head + (f"\n\n{escape(b.text)}" if b.text else "")
        await _show(callback, text, with_back([buy]))
        return
    await _show(callback, escape(b.text or b.title), with_back())


@router.message()
async def fallback(message: Message, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    await message.answer(welcome_text(runtime, db_user), reply_markup=await menu_markup(session, runtime))
