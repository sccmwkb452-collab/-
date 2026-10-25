"""Admin: users, their history, restrictions and balance corrections."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.states import UserSearch
from bot.callbacks import Adm
from bot.ui import Screen, show
from database.models import Order, Transaction, TxKind, User
from handlers.user.profile import TX_LABELS
from keyboards import admin as akb
from keyboards.user import btn, pager, rows
from services import users as users_service
from services.audit import log_action
from services.errors import InsufficientFunds
from services.formatting import clip, date, dt, esc, money, parse_signed_rubles, signed_money
from services.ledger import change_balance

router = Router(name="admin_users")
PAGE = 8


def _name(u: User) -> str:
    return f"@{u.username}" if u.username else (u.full_name or str(u.id))


@router.callback_query(Adm.filter(F.s == "users"))
async def users_list(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    total = await session.scalar(select(func.count(User.id))) or 0
    banned = await session.scalar(select(func.count(User.id)).where(User.is_banned.is_(True))) or 0
    pages = max(1, math.ceil(total / PAGE))
    page = min(max(callback_data.p, 0), pages - 1)
    items = (await session.execute(select(User).order_by(User.created_at.desc()).limit(PAGE).offset(page * PAGE))).scalars()
    buttons = [
        (f"{'⛔ ' if u.is_banned else ''}{clip(_name(u), 24)} · {money(u.balance)}", Adm(s="usr", id=u.id)) for u in items
    ]
    text = f"👥 <b>Пользователи</b>\n\nВсего: {total} · ограничено: {banned}\nНовые сверху."
    extra = [[btn("🔎 Найти по ID или @username", Adm(s="usearch"), style="primary")]]
    await show(callback, Screen(text, akb.listing(buttons, page, pages, lambda n: Adm(s="users", p=n), extra)))


@router.callback_query(Adm.filter(F.s == "usearch"))
async def search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserSearch.query)
    await show(callback, Screen("🔎 Отправьте Telegram ID или @username пользователя.", akb.cancel("users")))


@router.message(UserSearch.query, F.text)
async def search(message: Message, state: FSMContext, session: AsyncSession) -> None:
    u = await users_service.find_user(session, message.text)
    if u is None:
        await message.answer("Пользователь не найден. Он должен хотя бы раз запустить бота.", reply_markup=akb.cancel("users"))
        return
    await state.clear()
    await show(message, await user_screen(session, u))


async def user_screen(session: AsyncSession, u: User) -> Screen:
    await session.refresh(u)
    s = await users_service.profile_stats(session, u.id)
    referrer = await session.get(User, u.referrer_id) if u.referrer_id else None
    lines = [
        f"👤 <b>{esc(_name(u))}</b>",
        "",
        f"ID: <code>{u.id}</code>",
        f"Имя: {esc(u.full_name or '—')}",
        f"Регистрация: {date(u.created_at)} · активность: {dt(u.last_seen_at)}",
        f"Баланс: <b>{money(u.balance)}</b>",
        f"Покупок: {s.purchases} на {money(s.spent)}",
        f"Пригласил: {s.referrals} (с покупками {s.referrals_with_purchases}), заработал {money(s.referral_earned)}",
        f"Пригласивший: {esc(_name(referrer)) if referrer else '—'}",
        f"Бот заблокирован пользователем: {'да' if u.bot_blocked else 'нет'}",
    ]
    if u.is_banned:
        lines.append(f"\n⛔ <b>Доступ ограничен</b>: {esc(u.ban_reason or 'без причины')}")
    kb = rows(
        [btn("💳 Операции", Adm(s="utx", id=u.id)), btn("🛒 Заказы", Adm(s="uord", id=u.id))],
        [btn("➕➖ Изменить баланс", Adm(s="ubal", id=u.id), style="primary")],
        [
            btn("✅ Снять ограничение", Adm(s="uunban", id=u.id), style="success")
            if u.is_banned
            else btn("⛔ Ограничить доступ", Adm(s="uban", id=u.id), style="danger")
        ],
        [akb.back("users", "◀️ К пользователям")],
    )
    return Screen("\n".join(lines), kb)


async def _user(session: AsyncSession, uid: int, callback_answer: CallbackAnswer | None = None) -> User | None:
    u = await session.get(User, uid, populate_existing=True)
    if u is None and callback_answer is not None:
        callback_answer.text, callback_answer.show_alert = "Пользователь не найден", True
    return u


@router.callback_query(Adm.filter(F.s == "usr"))
async def user_card(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext, callback_answer: CallbackAnswer) -> None:
    await state.clear()
    u = await _user(session, callback_data.id, callback_answer)
    if u:
        await show(callback, await user_screen(session, u))


@router.callback_query(Adm.filter(F.s == "utx"))
async def user_transactions(callback: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    uid, page = callback_data.id, max(callback_data.p, 0)
    total = await session.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == uid)) or 0
    pages = max(1, math.ceil(total / 10))
    items = (
        await session.execute(
            select(Transaction).where(Transaction.user_id == uid).order_by(Transaction.id.desc()).limit(10).offset(page * 10)
        )
    ).scalars()
    lines = [f"💳 <b>Операции</b> · <code>{uid}</code>", ""]
    for t in items:
        extra = f" · {esc(t.comment)}" if t.comment else ""
        admin = f" · админ <code>{t.admin_id}</code>" if t.admin_id else ""
        lines.append(f"{TX_LABELS.get(t.kind, t.kind)} <b>{signed_money(t.amount)}</b> → {money(t.balance_after)}\n<i>{dt(t.created_at)}{extra}{admin}</i>")
    if total == 0:
        lines.append("Операций нет.")
    await show(
        callback,
        Screen("\n".join(lines), rows(pager(lambda n: Adm(s="utx", id=uid, p=n), page, pages), [akb.back("usr", "◀️ К пользователю", id=uid)])),
    )


@router.callback_query(Adm.filter(F.s == "uord"))
async def user_orders(callback: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    uid, page = callback_data.id, max(callback_data.p, 0)
    total = await session.scalar(select(func.count(Order.id)).where(Order.user_id == uid)) or 0
    pages = max(1, math.ceil(total / PAGE))
    items = (
        await session.execute(select(Order).where(Order.user_id == uid).order_by(Order.id.desc()).limit(PAGE).offset(page * PAGE))
    ).scalars()
    buttons = [
        (f"{'✅' if o.status == 'completed' else '↩️'} {o.number} · {clip(o.product_title, 20)} · {money(o.price)}", Adm(s="ord", id=o.id))
        for o in items
    ]
    await show(
        callback,
        Screen(
            f"🛒 <b>Заказы пользователя</b> <code>{uid}</code>\n\nВсего: {total}",
            akb.listing(buttons, page, pages, lambda n: Adm(s="uord", id=uid, p=n), back_to=akb.back("usr", "◀️ К пользователю", id=uid)),
        ),
    )


# ── balance correction ───────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.s == "ubal"))
async def balance_prompt(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(UserSearch.amount)
    await state.update_data(uid=callback_data.id)
    text = (
        "➕➖ <b>Корректировка баланса</b>\n\n"
        "Отправьте сумму со знаком: <code>+500</code> — начислить, <code>-200</code> — списать."
    )
    await show(callback, Screen(text, akb.cancel("usr", id=callback_data.id)))


@router.message(UserSearch.amount, F.text)
async def balance_amount(message: Message, state: FSMContext) -> None:
    uid = (await state.get_data())["uid"]
    amount = parse_signed_rubles(message.text)
    if amount is None or amount == 0 or abs(amount) > 10_000_000_00:
        await message.answer("Укажите сумму, например <code>+500</code> или <code>-200</code>.", reply_markup=akb.cancel("usr", id=uid))
        return
    await state.update_data(amount=amount)
    await state.set_state(UserSearch.reason)
    await message.answer(
        f"Сумма: <b>{signed_money(amount)}</b>\nОтправьте причину корректировки (обязательно, от 3 символов):",
        reply_markup=akb.cancel("usr", id=uid),
    )


@router.message(UserSearch.reason, F.text)
async def balance_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    reason = message.text.strip()
    if len(reason) < 3 or len(reason) > 256:
        await message.answer("Причина: от 3 до 256 символов.", reply_markup=akb.cancel("usr", id=data["uid"]))
        return
    await state.update_data(reason=reason)
    await message.answer(
        f"Подтвердите: <b>{signed_money(data['amount'])}</b> пользователю <code>{data['uid']}</code>\nПричина: {esc(reason)}",
        reply_markup=akb.confirm(Adm(s="ubalok", id=data["uid"]), Adm(s="usr", id=data["uid"])),
    )


@router.callback_query(Adm.filter(F.s == "ubalok"))
async def balance_apply(
    callback: CallbackQuery, callback_data: Adm, state: FSMContext, session: AsyncSession, callback_answer: CallbackAnswer
) -> None:
    data = await state.get_data()
    if data.get("uid") != callback_data.id or "amount" not in data or not data.get("reason"):
        callback_answer.text, callback_answer.show_alert = "Данные устарели, начните заново", True
        return
    await state.clear()  # clearing first makes a second tap a no-op
    amount, reason = data["amount"], data["reason"]
    try:
        await change_balance(session, callback_data.id, amount, TxKind.ADMIN, admin_id=callback.from_user.id, comment=reason)
    except InsufficientFunds:
        callback_answer.text, callback_answer.show_alert = "Нельзя списать больше, чем есть на балансе", True
        return
    await log_action(session, callback.from_user.id, "balance_adjust", f"user:{callback_data.id}", f"{amount} kop: {reason}")
    await session.commit()
    callback_answer.text = "Баланс изменён"
    try:
        await callback.bot.send_message(
            callback_data.id, f"💳 Баланс изменён администратором: <b>{signed_money(amount)}</b>\nПричина: {esc(reason)}"
        )
    except TelegramAPIError:
        pass
    await show(callback, await user_screen(session, await _user(session, callback_data.id)))


# ── restrictions ─────────────────────────────────────────────────────────────


@router.callback_query(Adm.filter(F.s == "uban"))
async def ban_prompt(callback: CallbackQuery, callback_data: Adm, state: FSMContext, admin_ids: frozenset[int], callback_answer: CallbackAnswer) -> None:
    if callback_data.id in admin_ids:
        callback_answer.text, callback_answer.show_alert = "Нельзя ограничить администратора", True
        return
    await state.set_state(UserSearch.ban_reason)
    await state.update_data(uid=callback_data.id)
    await show(callback, Screen("⛔ Отправьте причину ограничения (её увидит пользователь):", akb.cancel("usr", id=callback_data.id)))


@router.message(UserSearch.ban_reason, F.text)
async def ban(message: Message, state: FSMContext, session: AsyncSession) -> None:
    uid = (await state.get_data())["uid"]
    reason = message.text.strip()[:256]
    u = await _user(session, uid)
    await state.clear()
    if u is None:
        await message.answer("Пользователь не найден.")
        return
    u.is_banned, u.ban_reason = True, reason
    await log_action(session, message.from_user.id, "user_ban", f"user:{uid}", reason)
    await session.commit()
    await message.answer("⛔ Доступ ограничен")
    await show(message, await user_screen(session, u))


@router.callback_query(Adm.filter(F.s == "uunban"))
async def unban(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    u = await _user(session, callback_data.id, callback_answer)
    if u is None:
        return
    u.is_banned, u.ban_reason = False, None
    await log_action(session, callback.from_user.id, "user_unban", f"user:{u.id}")
    await session.commit()
    callback_answer.text = "Ограничение снято"
    await show(callback, await user_screen(session, u))
