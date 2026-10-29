"""Запуск парсера: нормализация → критерии → дубликаты → отказы → лимиты → очередь обращений."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.state import to_decimal
from app.core.audit import audit
from app.db.models import (
    Contact,
    Conversation,
    OutreachStatus,
    OutreachTask,
    Owner,
    ParserConfig,
    SearchResult,
    utcnow,
)
from app.parsers.base import Candidate, ParserAdapter, ParserError, SearchCriteria

logger = logging.getLogger(__name__)


@dataclass
class RunReport:
    scanned: int = 0
    queued: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    stopped_by: str | None = None

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def render(self) -> str:
        lines = [f"Просмотрено: {self.scanned}", f"Добавлено в очередь обращений: {self.queued}"]
        lines += [f"• отклонено ({k}): {v}" for k, v in sorted(self.rejected.items())]
        if self.stopped_by:
            lines.append(f"Остановлено: {self.stopped_by}")
        if self.error:
            lines.append(f"Ошибка: {self.error}")
        return "\n".join(lines)


def _haystack(c: Candidate) -> str:
    parts = [c.display_name, c.text, c.geo, c.username, *(f"{k} {v}" for k, v in c.attributes.items())]
    return " ".join(str(p) for p in parts if p).lower()


def matches_criteria(c: Candidate, cr: SearchCriteria) -> str | None:
    """None — подходит; иначе причина отказа."""
    if not c.reachable:
        return "нет контакта"
    if cr.target_role in ("seller", "buyer") and c.role and c.role != cr.target_role:
        return "другая роль"
    hay = _haystack(c)
    if cr.keywords and not any(k.lower() in hay for k in cr.keywords):
        return "нет ключевых слов"
    for key, needle in cr.filters.items():
        value = c.attributes.get(key) if key in c.attributes else getattr(c, key, None)
        if value is None or str(needle).lower() not in str(value).lower():
            return f"фильтр {key}"
    if cr.geo and (not c.geo or cr.geo.lower() not in str(c.geo).lower()):
        return "география"
    for key, bounds in cr.ranges.items():
        if key == "number":
            continue  # диапазон номеров обрабатывает сам адаптер
        raw: Any = c.price if key == "price" else c.attributes.get(key)
        value = raw if isinstance(raw, Decimal) else to_decimal(None if raw is None else str(raw))
        if value is None:
            return f"нет значения {key}"
        lo, hi = to_decimal(bounds.get("min")), to_decimal(bounds.get("max"))
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            return f"вне диапазона {key}"
    return None


async def _find_contact(session: AsyncSession, owner_id: int, c: Candidate) -> Contact | None:
    conds = []
    if c.telegram_user_id:
        conds.append(Contact.telegram_user_id == c.telegram_user_id)
    if c.username:
        conds.append(Contact.username == c.username.lower())
    if not conds:
        return None
    return await session.scalar(select(Contact).where(Contact.owner_id == owner_id, or_(*conds)))


async def _queued_count(session: AsyncSession, owner_id: int, parser_id: int | None, since=None) -> int:
    q = select(func.count(OutreachTask.id)).where(
        OutreachTask.owner_id == owner_id,
        OutreachTask.status.notin_([OutreachStatus.CANCELLED, OutreachStatus.FAILED]),
    )
    if parser_id is not None:
        q = q.where(OutreachTask.parser_id == parser_id)
    if since is not None:
        q = q.where(OutreachTask.created_at >= since)
    return int(await session.scalar(q) or 0)


async def run_parser(session: AsyncSession, owner: Owner, cfg: ParserConfig, adapter: ParserAdapter) -> RunReport:
    report = RunReport()
    criteria = SearchCriteria.from_config(cfg)
    stop_after = int((cfg.stop_rules or {}).get("stop_after_matches", 10**9))
    day_ago = utcnow() - timedelta(days=1)
    cooldown = utcnow() - timedelta(days=owner.recontact_cooldown_days)
    seen_in_batch: set[str] = set()

    try:
        await adapter.connect()
        ok, msg = await adapter.validate()
        if not ok:
            raise ParserError(msg)
        async for raw in adapter.search(criteria):
            report.scanned += 1
            if report.scanned > criteria.max_results:
                report.stopped_by = f"лимит просмотра {criteria.max_results}"
                break
            cand = adapter.normalize_result(raw)
            if cand is None:
                report.reject("не нормализован")
                continue
            key = cand.external_id
            if key in seen_in_batch:
                report.reject("дубликат в выдаче")
                continue
            seen_in_batch.add(key)
            if await session.scalar(select(SearchResult.id).where(SearchResult.parser_id == cfg.id, SearchResult.external_id == key)):
                report.reject("уже найден ранее")
                continue

            decision, reason, contact = "queued", None, None
            mismatch = matches_criteria(cand, criteria)
            if mismatch:
                decision, reason = "rejected", mismatch
            else:
                contact = await _find_contact(session, owner.id, cand)
                if contact and contact.opted_out:
                    decision, reason = "opted_out", "отказался от общения"
                elif contact and contact.last_contacted_at and contact.last_contacted_at >= cooldown:
                    decision, reason = "duplicate", "недавно уже обращались"
                elif contact and await session.scalar(
                    select(Conversation.id).where(Conversation.contact_id == contact.id)
                ):
                    decision, reason = "duplicate", "диалог уже существует"
                elif contact and await session.scalar(
                    select(OutreachTask.id).where(
                        OutreachTask.contact_id == contact.id,
                        OutreachTask.status.in_([OutreachStatus.PENDING_APPROVAL, OutreachStatus.APPROVED,
                                                 OutreachStatus.MANUAL_REQUIRED]),
                    )
                ):
                    decision, reason = "duplicate", "уже в очереди"
                elif await _queued_count(session, owner.id, cfg.id) >= cfg.total_contact_limit:
                    decision, reason = "limit", "общий лимит парсера"
                elif await _queued_count(session, owner.id, cfg.id, since=day_ago) >= cfg.daily_contact_limit:
                    decision, reason = "limit", "дневной лимит парсера"

            if decision == "queued":
                if contact is None:
                    contact = Contact(
                        owner_id=owner.id, telegram_user_id=cand.telegram_user_id,
                        username=cand.username.lower() if cand.username else None,
                        display_name=cand.display_name, source=f"parser:{cfg.name}", profile=cand.profile(),
                    )
                    session.add(contact)
                    await session.flush()
                session.add(OutreachTask(
                    owner_id=owner.id, contact_id=contact.id, parser_id=cfg.id,
                    status=OutreachStatus.PENDING_APPROVAL if owner.outreach_requires_approval else OutreachStatus.APPROVED,
                ))
                report.queued += 1
            else:
                report.reject(reason or decision)
            if decision == "limit":
                # Не запоминаем: после сброса лимита контакт можно будет рассмотреть снова.
                report.stopped_by = reason
                break
            session.add(SearchResult(
                owner_id=owner.id, parser_id=cfg.id, external_id=key, contact_id=contact.id if contact else None,
                data=cand.profile(), decision=decision, reason=reason,
            ))
            await session.flush()
            if report.queued >= stop_after:
                report.stopped_by = f"найдено {stop_after} подходящих"
                break
        cfg.status = "ok"
        cfg.last_error = None
    except ParserError as exc:
        report.error = str(exc)
        cfg.status = "error"
        cfg.last_error = str(exc)
    finally:
        await adapter.disconnect()
        cfg.last_run_at = utcnow()
    await audit(session, "parser_run", "error" if report.error else "ok", owner_id=owner.id, parser=cfg.name,
                error=report.error, scanned=report.scanned, queued=report.queued, rejected=report.rejected)
    return report
