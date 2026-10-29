"""Финансовые ограничения: валюты, лимиты, дневной бюджет, автоматический режим."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ACTIVE_DEAL_STATUSES, BUDGET_DEAL_STATUSES, Deal, TradeBotConfig, TradingPolicy, utcnow


@dataclass
class PolicyCheck:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


async def spent_today(session: AsyncSession, owner_id: int, currency: str, exclude_deal_id: int | None = None) -> Decimal:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = select(func.coalesce(func.sum(Deal.total), 0)).where(
        Deal.owner_id == owner_id,
        Deal.side == "buy",
        Deal.currency == currency,
        Deal.status.in_([s.value for s in BUDGET_DEAL_STATUSES]),
        Deal.funds_committed_at >= start,
    )
    if exclude_deal_id:
        q = q.where(Deal.id != exclude_deal_id)
    return Decimal(str(await session.scalar(q) or 0))


async def check_deal_policy(
    session: AsyncSession,
    policy: TradingPolicy,
    deal: Deal,
    bot: TradeBotConfig,
    *,
    automatic: bool,
    for_payment: bool = False,
) -> PolicyCheck:
    res = PolicyCheck()
    p = res.problems
    if not bot.currencies:
        p.append("Для торгового бота не заданы разрешённые валюты.")
    elif deal.currency not in bot.currencies:
        p.append(f"Валюта {deal.currency} не разрешена для @{bot.bot_username}.")
    if bot.supported_currencies and deal.currency not in bot.supported_currencies:
        p.append(f"@{bot.bot_username} не поддерживает валюту {deal.currency}.")
    if deal.total <= 0 or deal.unit_price <= 0 or deal.quantity <= 0:
        p.append("Некорректные сумма или количество.")
    if policy.max_deal_amount is not None and deal.total > policy.max_deal_amount:
        p.append(f"Сумма {deal.total} больше лимита на сделку {policy.max_deal_amount}.")

    active = await session.scalar(
        select(func.count(Deal.id)).where(
            Deal.owner_id == deal.owner_id, Deal.id != deal.id, Deal.status.in_([s.value for s in ACTIVE_DEAL_STATUSES])
        )
    )
    if active >= policy.max_concurrent_deals:
        p.append(f"Уже {active} активных сделок (лимит {policy.max_concurrent_deals}).")

    if deal.side == "buy":
        if policy.daily_budget is not None:
            if policy.budget_currency and policy.budget_currency != deal.currency:
                p.append(f"Дневной бюджет задан в {policy.budget_currency}, сделка в {deal.currency} — пересчёт не выполняется.")
            else:
                spent = await spent_today(session, deal.owner_id, deal.currency, exclude_deal_id=deal.id)
                if spent + deal.total > policy.daily_budget:
                    p.append(f"Превышение дневного бюджета: потрачено {spent}, сделка {deal.total}, бюджет {policy.daily_budget}.")
        elif automatic or for_payment:
            p.append("Не задан дневной бюджет — автоматические и API-оплаты запрещены.")

    if automatic:
        if not policy.auto_mode_enabled:
            p.append("Автоматический режим сделок выключен.")
        if for_payment and not policy.auto_pay_enabled:
            p.append("Автоматическая оплата выключена.")
        if policy.auto_categories and (deal.product_type or "") not in policy.auto_categories:
            p.append(f"Категория «{deal.product_type}» не входит в разрешённые для авто-режима.")
        if not policy.auto_currencies or deal.currency not in policy.auto_currencies:
            p.append(f"Валюта {deal.currency} не разрешена для авто-режима.")
        if policy.auto_max_price is None:
            p.append("Не задана максимальная цена для авто-режима.")
        elif deal.unit_price > policy.auto_max_price:
            p.append(f"Цена {deal.unit_price} выше максимума авто-режима {policy.auto_max_price}.")
        if policy.auto_allowed_sellers and deal.counterparty_telegram_id not in policy.auto_allowed_sellers:
            p.append("Продавец не входит в список допустимых для авто-режима.")
        if policy.repeat_purchase_cooldown_hours and deal.contact_id:
            since = utcnow() - timedelta(hours=policy.repeat_purchase_cooldown_hours)
            recent = await session.scalar(
                select(func.count(Deal.id)).where(
                    Deal.owner_id == deal.owner_id, Deal.contact_id == deal.contact_id, Deal.id != deal.id,
                    Deal.status.in_([s.value for s in BUDGET_DEAL_STATUSES]), Deal.funds_committed_at >= since,
                )
            )
            if recent:
                p.append(f"Повторная покупка у этого продавца раньше чем через {policy.repeat_purchase_cooldown_hours} ч.")
    return res
