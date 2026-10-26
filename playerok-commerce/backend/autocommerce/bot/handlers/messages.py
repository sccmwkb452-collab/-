"""💬 Сообщения покупателей: integration status, list, record a message,
autoresponder test and rules, reviews."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.enums import MessageStatus
from ...database.models import AutoresponderRule, CustomerMessage, Order
from ...integrations.marketplace.playerok_manual import get_marketplace
from ...services import messages, orders
from ...services.audit import Actor, audit
from ...shared.errors import DomainError, NotFound
from ...shared.timeutil import fmt_dt
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, empty, esc, kb, nav, pager, short

router = make_router("messages")
PER_PAGE = 8
STATUS_ICON = {
    MessageStatus.NEW: "🆕",
    MessageStatus.SUGGESTED: "💡",
    MessageStatus.ESCALATED: "🧑‍💼",
    MessageStatus.HANDLED: "✅",
    MessageStatus.AUTO_REPLIED: "🤖",
}


@router.callback_query(F.data == "msg:home")
async def home(cb: CallbackQuery, session: AsyncSession) -> None:
    market = get_marketplace()
    counts = dict((await session.execute(select(CustomerMessage.status, func.count()).group_by(CustomerMessage.status))).all())
    lines = [
        "💬 <b>Сообщения покупателей</b>",
        SEP,
        f"Интеграция: <b>{esc(market.title)}</b>",
        "🔴 Получение сообщений: недоступно" if not market.supports("fetch_messages") else "🟢 Получение сообщений: доступно",
        f"<i>{esc(market.reason('fetch_messages'))}</i>" if not market.supports("fetch_messages") else "",
        "🔴 Ответ через API: недоступен — ответы готовятся для копирования"
        if not market.supports("send_messages")
        else "🟢 Ответ через API: доступен",
        "",
        f"🆕 Новые: {counts.get(MessageStatus.NEW, 0)} · 💡 с ответом: {counts.get(MessageStatus.SUGGESTED, 0)} · 🧑‍💼 у оператора: {counts.get(MessageStatus.ESCALATED, 0)}",
    ]
    await show(
        cb,
        "\n".join(x for x in lines if x is not None),
        kb(
            [b("📥 Записать сообщение", "msg:new:0", style="primary"), b("⭐ Внести отзыв", "msg:review:0")],
            [b("🆕 Необработанные", "msg:list:open:1"), b("📋 Все", "msg:list:all:1")],
            [b("🧪 Проверить автоответчик", "msg:test"), b("🤖 Правила", "msg:rules")],
            nav(),
        ),
    )


@router.callback_query(F.data.startswith("msg:list:"))
async def message_list(cb: CallbackQuery, session: AsyncSession) -> None:
    _, _, flt, page = cb.data.split(":")
    page_n = int(page)
    stmt = select(CustomerMessage).where(CustomerMessage.direction == "in")
    if flt == "open":
        stmt = stmt.where(CustomerMessage.status.in_([MessageStatus.NEW, MessageStatus.SUGGESTED, MessageStatus.ESCALATED]))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(CustomerMessage.id.desc()).offset((page_n - 1) * PER_PAGE).limit(PER_PAGE))).scalars().all()
    buttons = [[b(f"{STATUS_ICON[m.status]} {short(m.buyer_name or '—', 12)}: {short(m.text, 28)}", f"msg:open:{m.id}")] for m in rows]
    text = f"💬 <b>{'Необработанные' if flt == 'open' else 'Все сообщения'}</b> · {total}\n{SEP}" + (
        "" if rows else "\n" + empty("Сообщений нет")
    )
    await show(cb, text, kb(*buttons, pager(f"msg:list:{flt}", page_n, total, PER_PAGE), nav("msg:home")))


async def message_card(session: AsyncSession, message_id: int) -> tuple[str, object]:
    m = await session.get(CustomerMessage, message_id)
    if m is None:
        raise NotFound("Сообщение не найдено")
    order = await session.get(Order, m.order_id) if m.order_id else None
    lines = [
        f"{STATUS_ICON[m.status]} <b>Сообщение #{m.id}</b>",
        SEP,
        f"Покупатель: {esc(m.buyer_name or '—')}",
        f"Заказ: {esc(order.number) if order else '—'}",
        f"Время: {fmt_dt(m.received_at)}",
        f"\n💬 {esc(m.text)}",
    ]
    if m.problem_hint:
        lines.append(f"\n⚠️ {esc(m.problem_hint)}")
    rows = []
    if m.suggested_reply:
        lines.append(f"\n💡 Готовый ответ:\n<code>{esc(m.suggested_reply)}</code>")
        if len(m.suggested_reply) <= 256:
            rows.append([b("📋 Скопировать ответ", copy=m.suggested_reply)])
    if m.handled_by:
        lines.append(f"\n✅ Обработал: {esc(m.handled_by)} · {fmt_dt(m.handled_at)}")
    rows.append([b("✅ Обработано", f"msg:done:{m.id}", style="success"), b("🧑‍💼 Передать оператору", f"msg:escalate:{m.id}")])
    if order:
        rows.append([b("🛒 Открыть заказ", f"ord:open:{order.id}"), b("⏸ Пауза автоматизации", f"ord:pause:{order.id}")])
    rows.append(nav("msg:list:open:1"))
    return "\n".join(lines), kb(*rows)


@router.callback_query(F.data.startswith("msg:open:"))
async def open_message(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await message_card(session, int(cb.data.split(":")[2]))
    await show(cb, text, markup)


@router.callback_query(F.data.regexp(r"^msg:(done|escalate):\d+$"))
async def set_status(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "messages.manage")
    _, action, mid = cb.data.split(":")
    await messages.set_status(session, int(mid), MessageStatus.HANDLED if action == "done" else MessageStatus.ESCALATED, actor)
    await cb.answer("Готово")
    text, markup = await message_card(session, int(mid))
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("msg:new:"))
async def new_message(cb: CallbackQuery, state: FSMContext, session: AsyncSession, actor: Actor) -> None:
    require(actor, "messages.manage")
    oid = int(cb.data.split(":")[2])
    order = await session.get(Order, oid) if oid else None
    if order:
        await ask(
            cb,
            state,
            "msg_text",
            f"Текст сообщения покупателя по заказу {order.number}:",
            back=f"ord:open:{oid}",
            order_ref=order.number,
            buyer=order.buyer_name,
        )
    else:
        await ask(cb, state, "msg_order", "Номер заказа (PO-…) или сделки PlayerOK. «-» — сообщение без заказа.", back="msg:home")


@on_input("msg_order")
async def message_order(message: Message, ctx: dict) -> None:
    ref = message.text.strip()
    buyer = None
    if ref != "-":
        order = await orders.find_order(ctx["session"], ref)
        if order is None:
            raise DomainError("Заказ не найден. Проверьте номер или отправьте «-»")
        ref, buyer = order.number, order.buyer_name
    else:
        ref = None
    await ctx["state"].update_data(kind="msg_buyer" if ref is None else "msg_text", order_ref=ref, buyer=buyer)
    await message.answer(
        "Ник покупателя на PlayerOK:" if ref is None else "Текст сообщения покупателя:", reply_markup=kb([b("✖️ Отмена", "cancel:msg:home")])
    )


@on_input("msg_buyer")
async def message_buyer(message: Message, ctx: dict) -> None:
    await ctx["state"].update_data(kind="msg_text", buyer=message.text.strip()[:120])
    await message.answer("Текст сообщения покупателя:", reply_markup=kb([b("✖️ Отмена", "cancel:msg:home")]))


@on_input("msg_text")
async def message_text(message: Message, ctx: dict) -> None:
    session = ctx["session"]
    order = await orders.find_order(session, ctx["order_ref"]) if ctx.get("order_ref") else None
    m = await messages.record_incoming(session, text=message.text, buyer_name=ctx.get("buyer"), order=order, actor=ctx["actor"])
    await ctx["state"].clear()
    text, markup = await message_card(session, m.id)
    await message.answer("📥 Сообщение записано. Уведомление и подсказки отправлены.\n\n" + text, reply_markup=markup)


@router.callback_query(F.data.startswith("msg:review:"))
async def new_review(cb: CallbackQuery, state: FSMContext, session: AsyncSession, actor: Actor) -> None:
    require(actor, "messages.manage")
    oid = int(cb.data.split(":")[2])
    order = await session.get(Order, oid) if oid else None
    await ask(
        cb,
        state,
        "msg_review",
        "Отзыв: <b>оценка 1–5</b> и текст через пробел.\nНапример: <code>5 Всё быстро, спасибо</code>",
        back=f"ord:open:{oid}" if order else "msg:home",
        order_ref=order.number if order else None,
    )


@on_input("msg_review")
async def review_input(message: Message, ctx: dict) -> None:
    text = message.text.strip()
    head, _, rest = text.partition(" ")
    if not head.isdigit() or not 1 <= int(head) <= 5:
        raise DomainError("Начните с оценки от 1 до 5")
    session = ctx["session"]
    order = await orders.find_order(session, ctx["order_ref"]) if ctx.get("order_ref") else None
    review = await messages.record_review(session, order=order, rating=int(head), text=rest, actor=ctx["actor"])
    await ctx["state"].clear()
    await message.answer(
        f"⭐ Отзыв сохранён ({review.sentiment.value}). Напоминания об отзыве по заказу остановлены.", reply_markup=kb(nav("msg:home"))
    )


@router.callback_query(F.data == "msg:test")
async def test(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(
        cb,
        state,
        "msg_test",
        "Напишите пример вопроса покупателя — покажу, какое правило сработает и какой будет ответ. Ничего не отправляется.",
        back="msg:home",
    )


@on_input("msg_test")
async def test_input(message: Message, ctx: dict) -> None:
    result = await messages.test_rules(ctx["session"], message.text, None)
    await ctx["state"].clear()
    lines = [
        "🧪 <b>Проверка автоответчика</b>",
        SEP,
        f"Правило: <b>{esc(result['rule'] or 'не найдено')}</b>",
        f"Действие: {esc(result['action'])}",
        f"Причина: {esc(result['reason'])}",
    ]
    if result["reply"]:
        lines.append(f"\nОтвет:\n<code>{esc(result['reply'])}</code>")
    await message.answer("\n".join(lines), reply_markup=kb([b("🧪 Ещё раз", "msg:test")], nav("msg:home")))


@router.callback_query(F.data == "msg:rules")
async def rules(cb: CallbackQuery, session: AsyncSession) -> None:
    rows = (await session.execute(select(AutoresponderRule).order_by(AutoresponderRule.priority, AutoresponderRule.id))).scalars().all()
    lines = ["🤖 <b>Правила автоответчика</b>", "<i>условие → действие, по приоритету (меньше — раньше)</i>", SEP]
    for r in rows:
        lines.append(f"{'🟢' if r.enabled else '⚪️'} <b>{r.priority}. {esc(r.name)}</b> → {esc(r.action)} · срабатываний: {r.hits}")
        lines.append(f"   <i>{esc(short(', '.join(map(str, r.patterns)), 80))}</i>")
    buttons = [[b(f"{'⏸ Выкл' if r.enabled else '▶️ Вкл'}: {short(r.name, 28)}", f"msg:rule:{r.id}")] for r in rows]
    lines.append("\n<i>Тексты и условия правил редактируются в веб-панели (Автонастройки → Автоответчик).</i>")
    await show(cb, "\n".join(lines), kb(*buttons, nav("msg:home")))


@router.callback_query(F.data.startswith("msg:rule:"))
async def toggle_rule(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "autosettings.manage")
    rule = await session.get(AutoresponderRule, int(cb.data.split(":")[2]))
    if rule is None:
        raise NotFound("Правило не найдено")
    rule.enabled = not rule.enabled
    await audit(session, actor, "autoresponder.rule_toggle", entity_type="rule", entity_id=rule.id, details={"enabled": rule.enabled})
    await rules(cb, session)
