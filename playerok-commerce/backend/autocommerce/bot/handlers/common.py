"""/start, main menu, dashboard, confirmations, free-text input dispatch."""

from __future__ import annotations

from aiogram import F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.enums import ORDER_STATUS_LABELS, MessageStatus, OrderStatus
from ...database.models import CustomerMessage, Order
from ...services import analytics, app_settings, auth, health
from ...services.audit import Actor
from ...shared.errors import DomainError
from ...shared.timeutil import ago, fmt_dt
from ..core import INPUTS, Input, make_router, show
from ..ui import SEP, b, esc, kb, money

router = make_router("common")

MENU = [
    [("🏠 Главная панель", "dash"), ("📦 Товары", "prd:list:all:1")],
    [("🛒 Заказы", "ord:home"), ("💬 Сообщения покупателей", "msg:home")],
    [("📈 Аналитика", "ana:30d"), ("💰 Прибыль и цены", "prc:home")],
    [("🔎 Поиск товаров", "res:home"), ("🏪 Поставщики", "sup:list")],
    [("🖼 Генератор изображений", "img:home"), ("📝 Объявления", "lst:home")],
    [("⚙️ Автонастройки", "as:home"), ("📊 Отчёты", "rep:home")],
    [("🛡 Безопасность", "sec:home"), ("🔔 Уведомления", "ntf:home")],
    [("🧾 Журнал операций", "log:home"), ("⚙️ Настройки", "set:home")],
]


async def badges(session: AsyncSession) -> str:
    live = await app_settings.is_live(session)
    stopped = await app_settings.automation_stopped(session)
    attention = (await session.execute(select(func.count()).where(Order.needs_attention.is_(True)))).scalar_one()
    unread = (
        await session.execute(select(func.count()).where(CustomerMessage.status.in_([MessageStatus.NEW, MessageStatus.ESCALATED])))
    ).scalar_one()
    parts = ["🟢 Боевой режим" if live else "🧪 Тестовый режим"]
    if stopped:
        parts.append("🛑 Автоматизация остановлена")
    if attention:
        parts.append(f"⚠️ Внимание: {attention}")
    if unread:
        parts.append(f"💬 Новых: {unread}")
    return " · ".join(parts)


async def menu_screen(session: AsyncSession, actor: Actor) -> tuple[str, object]:
    shop = (await app_settings.get_setting(session, "shop.profile"))["name"]
    text = f"🎮 <b>{esc(shop)}</b>\n<i>PlayerOK Auto Commerce</i>\n{SEP}\n{await badges(session)}\n\nВыберите раздел:"
    rows = [[b(label, cb) for label, cb in row] for row in MENU]
    return text, kb(*rows)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, session: AsyncSession, actor: Actor | None, state: FSMContext) -> None:
    await state.clear()
    if command.args and command.args.startswith("link_"):
        user = await auth.redeem_link_code(session, command.args[5:], message.from_user.id)
        await message.answer(f"✅ Telegram привязан к пользователю <b>{esc(user.display_name)}</b> ({esc(user.role.name)}).")
        actor = auth.actor_for(user, kind="telegram")
    if actor is None:
        return
    text, markup = await menu_screen(session, actor)
    await message.answer(text, reply_markup=markup)


@router.message(Command("menu"))
async def menu_cmd(message: Message, session: AsyncSession, actor: Actor, state: FSMContext) -> None:
    await state.clear()
    text, markup = await menu_screen(session, actor)
    await message.answer(text, reply_markup=markup)


@router.message(Command("id"))
async def my_id(message: Message) -> None:
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.callback_query(F.data == "home")
async def home(cb: CallbackQuery, session: AsyncSession, actor: Actor, state: FSMContext) -> None:
    await state.clear()
    text, markup = await menu_screen(session, actor)
    await show(cb, text, markup)


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_input(cb: CallbackQuery, session: AsyncSession, actor: Actor, state: FSMContext) -> None:
    await state.clear()
    await cb.answer("Отменено")
    back = cb.data.split(":", 1)[1]
    if back == "home":
        text, markup = await menu_screen(session, actor)
        await show(cb, text, markup)
    else:
        await show(cb, "Ввод отменён.", kb([b("‹ Назад", back), b("🏠 Меню", "home")]))


@router.callback_query(F.data == "dash")
async def dashboard(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    today = await analytics.metrics(session, analytics.period("today"))
    week = await analytics.metrics(session, analytics.period("7d"))
    hs = await health.status(session)
    open_rows = (
        await session.execute(
            select(Order.status, func.count())
            .where(Order.status.not_in([OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REFUND]))
            .group_by(Order.status)
        )
    ).all()
    totals = await analytics.recorded_totals(session)
    lines = [
        "🏠 <b>Главная панель</b>",
        SEP,
        await badges(session),
        "",
        "<b>Сегодня</b>",
        f"🛒 Заказов: <b>{today['orders']}</b> · ✅ завершено: <b>{today['completed']}</b>",
        f"💰 Выручка: <b>{money(today['revenue'])}</b> · 📈 прибыль: <b>{money(today['net_profit'])}</b>",
        "",
        "<b>7 дней</b>",
        f"🛒 {week['orders']} заказов · 💰 {money(week['revenue'])} · 📈 {money(week['net_profit'])}",
    ]
    if week["orders_without_cost"]:
        lines.append(f"⚠️ Без себестоимости: {week['orders_without_cost']} — прибыль по ним не учтена")
    if open_rows:
        lines += ["", "<b>Открытые заказы</b>"] + [f"{ORDER_STATUS_LABELS[s]}: {c}" for s, c in open_rows]
    worker = hs.get("worker", {})
    bot = hs.get("bot", {})
    lines += [
        "",
        "<b>Система</b>",
        f"🗄 База данных: {'🟢' if hs['database']['ok'] else '🔴'}",
        f"⚙️ Worker: {'🟢' if worker.get('ok') else '🔴'} ({ago(_dt(worker.get('last_seen_at')))})",
        f"🤖 Бот: {'🟢' if bot.get('ok') else '🟡'} ({ago(_dt(bot.get('last_seen_at')))})",
        f"📬 Очередь: {hs['queue'].get('queued', 0)} в ожидании · {hs['queue'].get('failed', 0)} с ошибкой",
        "",
        f"📥 Данных в системе: сделок {totals['deals']}, отзывов {totals['reviews']}, транзакций {totals['transactions']}",
        f"🕒 Обновлено: {fmt_dt(_dt(totals['last_update']))}",
        "<i>PlayerOK без API: заказы вносятся вручную или импортом CSV.</i>",
    ]
    await show(
        cb,
        "\n".join(lines),
        kb(
            [b("⚠️ Требуют внимания", "ord:list:attention:1", style="primary"), b("🔄 Обновить", "dash")],
            [b("➕ Новый заказ", "ord:new"), b("📈 Аналитика", "ana:30d")],
            [b("🏠 Меню", "home")],
        ),
    )


def _dt(value):
    from datetime import datetime

    return datetime.fromisoformat(value) if value else None


@router.message(Input.waiting, F.text)
async def free_text(message: Message, state: FSMContext, session: AsyncSession, actor: Actor) -> None:
    data = await state.get_data()
    handler = INPUTS.get(data.get("kind", ""))
    if handler is None:
        await state.clear()
        await message.answer("Ввод устарел. Откройте раздел заново: /menu")
        return
    if message.text.strip().lower() in ("отмена", "/cancel", "cancel"):
        await state.clear()
        await message.answer("Ввод отменён.", reply_markup=kb([b("🏠 Меню", "home")]))
        return
    try:
        await handler(message, {"state": state, "session": session, "actor": actor, **data})
    except DomainError as exc:
        await session.rollback()  # nothing from a failed input is saved
        await message.answer(
            f"⚠️ {esc(exc.message)}\nПопробуйте ещё раз или нажмите «Отмена».",
            reply_markup=kb([b("✖️ Отмена", f"cancel:{data.get('back', 'home')}")]),
        )


@router.message(F.text & ~F.text.startswith("/"))
async def stray_text(message: Message) -> None:
    await message.answer("Используйте кнопки меню.", reply_markup=kb([b("🏠 Меню", "home")]))
