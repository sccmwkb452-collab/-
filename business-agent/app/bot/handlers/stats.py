from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select

from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.ui import btn, kb
from app.db.models import (
    ACTIVE_DEAL_STATUSES,
    AuditLog,
    Contact,
    Conversation,
    ConversationMessage,
    Deal,
    DealStatus,
    SearchResult,
)

router = Router(name="stats")
PAGE = 15


async def _count(session, q):
    return await session.scalar(q) or 0


@router.callback_query(Cb.filter(F.s == "stats"))
async def stats(cq: CallbackQuery, session, owner):
    oid = owner.id
    conv_ids = select(Conversation.id).where(Conversation.owner_id == oid)
    msg = lambda sender: select(func.count(ConversationMessage.id)).where(  # noqa: E731
        ConversationMessage.conversation_id.in_(conv_ids), ConversationMessage.sender == sender)
    deals = (await session.scalars(select(Deal).where(Deal.owner_id == oid))).all()
    totals: dict[str, object] = {}
    fees: dict[str, object] = {}
    for d in deals:
        if d.status in (DealStatus.PAID, DealStatus.COMPLETED):
            totals[d.currency] = totals.get(d.currency, 0) + d.total
            fees[d.currency] = fees.get(d.currency, 0) + d.fees
    fmt = lambda m: ", ".join(f"{v.normalize()} {k}" for k, v in m.items()) or "0"  # noqa: E731
    integ_errors = await _count(session, select(func.count(AuditLog.id)).where(
        AuditLog.owner_id == oid, AuditLog.result == "error",
        AuditLog.action.in_(["parser_run", "deal_create", "deal_pay", "trade_bot_check", "agent_reply", "media_analyzed", "outreach"])))
    lines = [
        "<b>📊 Статистика</b>",
        f"Найдено контактов парсерами: {await _count(session, select(func.count(SearchResult.id)).where(SearchResult.owner_id == oid, SearchResult.decision == 'queued'))}",
        f"Контактов всего: {await _count(session, select(func.count(Contact.id)).where(Contact.owner_id == oid))}",
        f"Обработано диалогов: {await _count(session, select(func.count(Conversation.id)).where(Conversation.owner_id == oid))}",
        f"Отправлено агентом: {await _count(session, msg('agent'))}",
        f"Получено от собеседников: {await _count(session, msg('contact'))}",
        f"Активных переговоров: {await _count(session, select(func.count(Conversation.id)).where(Conversation.owner_id == oid, Conversation.state['conversation_stage'].as_string() == 'negotiation'))}",
        f"Сделок создано: {sum(1 for d in deals if d.status not in (DealStatus.DRAFT, DealStatus.AWAITING_CONFIRMATION, DealStatus.CANCELLED))}",
        f"Активных сделок: {sum(1 for d in deals if d.status in ACTIVE_DEAL_STATUSES)}",
        f"Завершено: {sum(1 for d in deals if d.status == DealStatus.COMPLETED)}",
        f"Неудачных операций: {sum(1 for d in deals if d.status == DealStatus.FAILED)}",
        f"Сумма оплаченных сделок: {escape(fmt(totals))}",
        f"Комиссии: {escape(fmt(fees))}",
        f"Ошибок интеграций: {integ_errors}",
    ]
    await show(cq, "\n".join(lines), kb([btn("🔄 Обновить", "stats")]))


RESULT_ICON = {"ok": "✅", "error": "❌", "blocked": "⛔️", "skipped": "➖", "unknown": "❓"}


@router.callback_query(Cb.filter(F.s == "log"))
async def log(cq: CallbackQuery, callback_data: Cb, session, owner):
    page = max(callback_data.i, 0)
    rows = (await session.scalars(select(AuditLog).where(AuditLog.owner_id == owner.id)
                                  .order_by(AuditLog.id.desc()).offset(page * PAGE).limit(PAGE))).all()
    lines = ["<b>📜 История действий</b>"]
    for r in rows:
        meta = " · ".join(filter(None, [
            f"диалог {r.conversation_id}" if r.conversation_id else None,
            f"парсер {r.parser}" if r.parser else None,
            f"бот @{r.trade_bot}" if r.trade_bot else None,
        ]))
        lines.append(f"{RESULT_ICON.get(r.result, r.result)} {r.created_at:%d.%m %H:%M} <b>{escape(r.action)}</b>"
                     + (f" ({escape(meta)})" if meta else "") + (f"\n   {escape(r.error[:200])}" if r.error else ""))
    if not rows:
        lines.append("Записей нет.")
    nav = []
    if page:
        nav.append(btn("⬅️ Новее", "log", "show", page - 1))
    if len(rows) == PAGE:
        nav.append(btn("Старее ➡️", "log", "show", page + 1))
    await show(cq, "\n".join(lines), kb(nav))
