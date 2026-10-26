"""Daily and weekly summaries sent to Telegram (and shown on demand)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import OrderStatus, Severity
from ..database.models import Order
from ..shared.money import fmt_money
from ..shared.timeutil import local_today
from . import analytics
from .notifications import btn, notify


async def summary_text(session: AsyncSession, period_code: str) -> str:
    p = analytics.period(period_code)
    m = await analytics.metrics(session, p)
    attention = (await session.execute(select(func.count()).where(Order.needs_attention.is_(True)))).scalar_one()
    waiting = (
        await session.execute(select(func.count()).where(Order.status.in_([OrderStatus.READY_FOR_DELIVERY, OrderStatus.DELIVERED])))
    ).scalar_one()
    lines = [
        f"📅 <b>{p.label}</b> ({p.first_day:%d.%m}–{p.last_day:%d.%m})",
        "",
        f"🛒 Заказов: <b>{m['orders']}</b> · завершено: <b>{m['completed']}</b>",
        f"↩️ Возвратов: {m['refunds']} · ⚖️ споров: {m['disputes']} · ✖️ отмен: {m['cancelled']}",
        f"💰 Выручка: <b>{fmt_money(Decimal(m['revenue']))}</b>",
        f"💸 Закупка: {fmt_money(Decimal(m['purchase_costs']))} · комиссии: {fmt_money(Decimal(m['fees']))}",
        f"📈 Чистая прибыль: <b>{fmt_money(Decimal(m['net_profit']))}</b>" + (f" · маржа {m['margin_pct']} %" if m["margin_pct"] else ""),
    ]
    if m["orders_without_cost"]:
        lines.append(f"⚠️ Сделок без себестоимости: {m['orders_without_cost']} — прибыль по ним не учтена")
    if m["avg_check"]:
        lines.append(f"🧾 Средний чек: {fmt_money(Decimal(m['avg_check']))}")
    if m["reviews"]:
        lines.append(f"⭐ Отзывов: {m['reviews']} · средняя оценка {m['avg_review_rating']}")
    lines += ["", f"🔔 Требуют внимания: <b>{attention}</b> · ждут выдачи/подтверждения: {waiting}"]
    if m["integration_errors"]:
        lines.append(f"🛠 Ошибок интеграций: {m['integration_errors']}")
    return "\n".join(lines)


async def send_daily(session: AsyncSession) -> None:
    text = await summary_text(session, "yesterday")
    await notify(
        session,
        "report",
        "Ежедневный отчёт",
        text,
        severity=Severity.INFO,
        buttons=[[btn("📈 Аналитика", "ana:30d"), btn("🛒 Заказы", "ord:list:attention:1")]],
        dedupe_key=f"daily_report:{local_today().isoformat()}",
    )


async def send_weekly(session: AsyncSession) -> None:
    text = await summary_text(session, "7d")
    await notify(
        session, "report", "Недельный отчёт", text, severity=Severity.INFO, dedupe_key=f"weekly_report:{local_today().isoformat()}"
    )
