"""Фоновые задачи: обращения, сверка сделок, плановые запуски парсеров, курсы, очистка."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from html import escape

from sqlalchemy import delete, select

from app.bot.ui import STATUS_RU, deal_actions, deal_card
from app.core.dedup import purge_old
from app.db.models import (
    Contact,
    Conversation,
    ConversationMessage,
    Deal,
    DealStatus,
    ExchangeRate,
    OutreachStatus,
    OutreachTask,
    Owner,
    ParserConfig,
    TradeBotConfig,
    utcnow,
)
from app.parsers.pipeline import run_parser
from app.parsers.registry import build_adapter

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, ctx, business, outreach) -> None:
        self.ctx = ctx
        self.business = business
        self.outreach = outreach
        self._task: asyncio.Task | None = None
        self._last_daily = None
        self._last_rates = None
        # Экспоненциальная пауза между сверками одной сделки: 30 с → … → 1 ч.
        self._reconcile_backoff: dict[int, tuple[float, object]] = {}

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            for job in (self.outreach_tick, self.reconcile_deals, self.scheduled_parsers, self.refresh_rates, self.daily_cleanup):
                try:
                    await job()
                except Exception:  # noqa: BLE001 — одна упавшая задача не останавливает остальные
                    logger.exception("Ошибка фоновой задачи %s", job.__name__)
            await asyncio.sleep(self.ctx.settings.scheduler_interval_seconds)

    async def outreach_tick(self) -> None:
        async with self.ctx.sessions() as s:
            owner_ids = set((await s.scalars(select(OutreachTask.owner_id).where(
                OutreachTask.status == OutreachStatus.APPROVED))).all())
        for owner_id in owner_ids:
            await self.outreach.process_owner(owner_id)

    async def reconcile_deals(self) -> None:
        async with self.ctx.sessions() as s:
            deals = (await s.scalars(select(Deal).where(
                (Deal.status.in_([DealStatus.UNKNOWN, DealStatus.PAYING]))
                | ((Deal.status == DealStatus.CREATED) & (Deal.side == "sell") & Deal.external_deal_id.is_not(None)),
                Deal.updated_at < utcnow() - timedelta(seconds=30),
            ).limit(20))).all()
            now = utcnow()
            for deal in deals:
                delay, last = self._reconcile_backoff.get(deal.id, (30.0, None))
                if last is not None and (now - last).total_seconds() < delay:
                    continue
                before = deal.status
                step = await self.ctx.deals.reconcile(s, deal)
                self._reconcile_backoff[deal.id] = (min(delay * 2, 3600.0), now)
                await s.commit()
                if deal.status != before:
                    self._reconcile_backoff.pop(deal.id, None)
                    owner = await s.get(Owner, deal.owner_id)
                    contact = await s.get(Contact, deal.contact_id) if deal.contact_id else None
                    await self.business.notify(
                        owner.telegram_id,
                        f"🔄 Сделка #{deal.id}: {STATUS_RU.get(DealStatus(before))} → {STATUS_RU.get(DealStatus(deal.status))}\n"
                        f"{escape(step.message)}\n\n" + deal_card(deal, contact),
                        deal_actions(deal),
                    )

    async def scheduled_parsers(self) -> None:
        async with self.ctx.sessions() as s:
            parsers = (await s.scalars(select(ParserConfig).where(ParserConfig.enabled.is_(True)))).all()
            for cfg in parsers:
                hours = (cfg.stop_rules or {}).get("interval_hours")
                if not hours or (cfg.last_run_at and utcnow() - cfg.last_run_at < timedelta(hours=float(hours))):
                    continue
                owner = await s.get(Owner, cfg.owner_id)
                if owner.paused:
                    continue
                report = await run_parser(s, owner, cfg, build_adapter(cfg))
                await s.commit()
                if report.queued or report.error:
                    await self.business.notify(owner.telegram_id, f"🔎 Парсер «{escape(cfg.name)}» (по расписанию):\n"
                                                                  + escape(report.render()))

    async def refresh_rates(self) -> None:
        if self._last_rates and utcnow() - self._last_rates < timedelta(hours=1):
            return
        self._last_rates = utcnow()
        async with self.ctx.sessions() as s:
            cfg = await s.scalar(select(TradeBotConfig).where(TradeBotConfig.adapter == "cryptopay",
                                                              TradeBotConfig.is_active.is_(True)))
            if cfg is None or not self.ctx.settings.crypto_pay_api_token:
                return
            rates = await self.ctx.trade_adapters.for_config(cfg).exchange_rates()
            for (src, dst), rate in rates.items():
                row = await s.scalar(select(ExchangeRate).where(ExchangeRate.source_currency == src,
                                                                ExchangeRate.target_currency == dst,
                                                                ExchangeRate.provider == "cryptopay"))
                if row is None:
                    s.add(ExchangeRate(source_currency=src, target_currency=dst, rate=rate, provider="cryptopay"))
                else:
                    row.rate, row.fetched_at = rate, utcnow()
            await s.commit()

    async def daily_cleanup(self) -> None:
        if self._last_daily and utcnow() - self._last_daily < timedelta(hours=24):
            return
        self._last_daily = utcnow()
        async with self.ctx.sessions() as s:
            for owner in (await s.scalars(select(Owner))).all():
                cutoff = utcnow() - timedelta(days=owner.history_retention_days)
                await s.execute(delete(ConversationMessage).where(
                    ConversationMessage.created_at < cutoff,
                    ConversationMessage.conversation_id.in_(select(Conversation.id).where(Conversation.owner_id == owner.id)),
                ))
            await purge_old(s)
            await s.commit()
