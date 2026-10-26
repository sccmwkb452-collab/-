"""Buyer messages, reviews and the autoresponder.

Messages come from an integration (when one exists) or are recorded by the
operator. Each incoming message is matched against the autoresponder rules
(priority order). The reply is sent through the marketplace only when it
supports sending; otherwise it is prepared for the operator to copy.

Safety: a reply that claims the order is done is never produced unless the
order really is delivered or completed — such a match goes to the operator.
Only the buyer's public nickname and the message text are stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ORDER_STATUS_LABELS, LogResult, MessageDirection, MessageStatus, OrderStatus, Sentiment, Severity
from ..database.models import AutoresponderRule, CustomerMessage, Inventory, Order, Review
from ..integrations.marketplace.playerok_manual import get_marketplace
from ..shared.errors import DomainError, NotFound
from ..shared.masking import mask_buyer
from ..shared.timeutil import fmt_dt, local_tz, utcnow
from . import hints, jobs
from . import templates as tpl
from .audit import Actor, audit, automation_log
from .autosettings import is_active
from .notifications import btn, esc, notify

MAX_PATTERN = 200
DELIVERED_STATES = (OrderStatus.DELIVERED, OrderStatus.COMPLETED)


@dataclass
class RuleMatch:
    rule: AutoresponderRule | None
    action: str  # reply | escalate | status | neutral | manual
    text: str | None
    reason: str


def _matches(rule: AutoresponderRule, text: str) -> bool:
    lowered = text.lower()
    if rule.match_type == "keywords":
        return any(str(p).lower() in lowered for p in rule.patterns or [])
    if rule.match_type == "regex":
        for pattern in rule.patterns or []:
            if len(str(pattern)) > MAX_PATTERN:
                continue
            try:
                if re.search(str(pattern), text, re.IGNORECASE):
                    return True
            except re.error:
                continue
    return False


def validate_rule(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("name") or "").strip()
    if not name:
        raise DomainError("Укажите название правила")
    match_type = data.get("match_type", "keywords")
    if match_type not in ("keywords", "regex"):
        raise DomainError("Тип условия: keywords или regex")
    patterns = data.get("patterns") or []
    if isinstance(patterns, str):
        patterns = [p.strip() for p in patterns.split(",") if p.strip()]
    if not patterns:
        raise DomainError("Добавьте хотя бы одно ключевое слово")
    if match_type == "regex":
        for p in patterns:
            if len(p) > MAX_PATTERN:
                raise DomainError(f"Выражение длиннее {MAX_PATTERN} символов")
            if re.search(r"\([^)]*[+*][^)]*\)[+*{]", p):
                raise DomainError("Вложенные повторы в регулярном выражении запрещены (риск зависания)")
            try:
                re.compile(p)
            except re.error as exc:
                raise DomainError(f"Ошибка в выражении: {exc}") from exc
    action = data.get("action", "reply")
    if action not in ("reply", "escalate", "status"):
        raise DomainError("Действие: reply, escalate или status")
    template = str(data.get("reply_template") or "")
    problems = tpl.validate_template(template)
    if problems:
        raise DomainError("; ".join(problems))
    statuses = [s for s in (data.get("order_statuses") or []) if s in {x.value for x in OrderStatus}]
    return {
        "name": name[:120],
        "priority": int(data.get("priority", 100)),
        "enabled": bool(data.get("enabled", True)),
        "match_type": match_type,
        "patterns": [str(p)[:MAX_PATTERN] for p in patterns][:50],
        "order_statuses": statuses,
        "action": action,
        "reply_template": template[:2000],
    }


async def _availability(session: AsyncSession, order: Order | None) -> str:
    if order is None or not order.items:
        return "уточню наличие и отвечу"
    inv = await session.get(Inventory, order.items[0].product_id)
    if inv is None:
        return "уточню наличие и отвечу"
    if inv.unlimited or inv.quantity_available > 0:
        return "в наличии"
    return "закончился, уточню сроки поставки"


async def match(session: AsyncSession, text: str, order: Order | None) -> RuleMatch:
    rules = (
        await session.execute(
            select(AutoresponderRule).where(AutoresponderRule.enabled.is_(True)).order_by(AutoresponderRule.priority, AutoresponderRule.id)
        )
    ).scalars()
    context = await hints.order_context(session, order, availability=await _availability(session, order))
    for rule in rules:
        if rule.order_statuses and (order is None or order.status.value not in rule.order_statuses):
            continue
        if not _matches(rule, text):
            continue
        if rule.action == "escalate":
            reply = tpl.render(rule.reply_template, context) if rule.reply_template else None
            return RuleMatch(rule, "escalate", reply, f"Правило «{rule.name}»: передать оператору")
        if rule.action == "status" and order is None:
            return RuleMatch(rule, "manual", None, f"Правило «{rule.name}»: заказ не найден — нужен оператор")
        reply = tpl.render(rule.reply_template, context)
        if tpl.claims_completion(reply) and (order is None or order.status not in DELIVERED_STATES):
            return RuleMatch(rule, "manual", None, f"Правило «{rule.name}» обещает выполнение, но заказ не выдан — нужен оператор")
        return RuleMatch(rule, rule.action, reply, f"Правило «{rule.name}»")
    active, cfg = await is_active(session, "autoresponder")
    if cfg.get("fallback") == "neutral":
        return RuleMatch(None, "neutral", tpl.render(cfg.get("neutral_text", ""), context), "Вопрос не распознан: нейтральный ответ")
    return RuleMatch(None, "manual", None, "Вопрос не распознан: нужен оператор")


def _in_window(now_local: datetime, start: str, end: str) -> bool:
    s, e = time.fromisoformat(start), time.fromisoformat(end)
    t = now_local.time()
    return s <= t < e if s < e else (t >= s or t < e)


async def record_incoming(
    session: AsyncSession,
    *,
    text: str,
    buyer_name: str | None,
    order: Order | None,
    actor: Actor,
    external_id: str | None = None,
    chat_id: str | None = None,
    source: str = "manual",
    received_at: datetime | None = None,
) -> CustomerMessage:
    text = text.strip()
    if not text:
        raise DomainError("Пустое сообщение")
    buyer = (buyer_name or (order.buyer_name if order else None) or "").strip()[:120] or None
    if external_id:
        dup = (
            await session.execute(
                select(CustomerMessage).where(CustomerMessage.marketplace == "playerok", CustomerMessage.external_id == external_id)
            )
        ).scalar_one_or_none()
        if dup is not None:
            return dup
    message = CustomerMessage(
        external_id=external_id,
        chat_external_id=chat_id,
        order_id=order.id if order else None,
        buyer_name=buyer,
        direction=MessageDirection.INCOMING,
        text=text[:4000],
        source=source,
        received_at=received_at or utcnow(),
    )
    session.add(message)
    await session.flush()
    await audit(session, actor, "message.record", entity_type="customer_message", entity_id=message.id)

    previous = 0
    if buyer:
        previous = (
            await session.execute(
                select(func.count()).where(
                    CustomerMessage.buyer_name == buyer,
                    CustomerMessage.id != message.id,
                    CustomerMessage.direction == MessageDirection.INCOMING,
                )
            )
        ).scalar_one()
    suggestions: list[tuple[str, str]] = []
    greet_active, greet_cfg = await is_active(session, "greeting")
    if greet_active and (previous == 0 or not greet_cfg.get("only_first", True)):
        ctx = await hints.order_context(session, order, buyer=buyer or "покупатель")
        suggestions.append(("👋 Приветствие", tpl.render(greet_cfg["text"], ctx)))
        await automation_log(session, "greeting", "suggest", LogResult.SUGGESTED, buyer or "", order_id=message.order_id)
    off_active, off_cfg = await is_active(session, "offline_text")
    if off_active and _in_window(utcnow().astimezone(local_tz()), off_cfg["offline_from"], off_cfg["offline_to"]):
        ctx = await hints.order_context(session, order, buyer=buyer or "покупатель")
        suggestions.append(("💤 Не в сети", tpl.render(off_cfg["text"], ctx)))
        await automation_log(session, "offline_text", "suggest", LogResult.SUGGESTED, buyer or "", order_id=message.order_id)

    ar_active, _ = await is_active(session, "autoresponder")
    result = await match(session, text, order)
    if ar_active and result.rule is not None:
        result.rule.hits += 1
        result.rule.last_hit_at = utcnow()
    message.matched_rule_id = result.rule.id if result.rule else None
    message.problem_hint = result.reason[:255] if result.action in ("escalate", "manual") else None
    if ar_active and result.text and result.action in ("reply", "status", "neutral"):
        message.suggested_reply = result.text
        message.status = MessageStatus.SUGGESTED
        suggestions.append(("🤖 Автоответчик", result.text))
        await automation_log(
            session,
            "autoresponder",
            result.action,
            LogResult.SUGGESTED,
            f"{result.reason}: {result.text}",
            order_id=message.order_id,
            details={"rule_id": message.matched_rule_id},
        )
    elif result.action == "escalate":
        message.status = MessageStatus.ESCALATED
        if result.text:
            message.suggested_reply = result.text
        await automation_log(session, "autoresponder", "escalate", LogResult.OK, result.reason, order_id=message.order_id)
    elif ar_active:
        await automation_log(session, "autoresponder", "manual", LogResult.SKIPPED, result.reason, order_id=message.order_id)

    await _notify_message(session, message, order, suggestions, escalate=result.action == "escalate")
    ignore_active, ignore_cfg = await is_active(session, "ignore_text")
    if ignore_active:
        await jobs.enqueue(
            session,
            "message.ignore_check",
            {"message_id": message.id},
            dedupe_key=f"ignore:{message.id}",
            run_after=utcnow() + timedelta(minutes=int(ignore_cfg["after_minutes"])),
        )
    return message


async def _notify_message(
    session: AsyncSession, message: CustomerMessage, order: Order | None, suggestions: list[tuple[str, str]], *, escalate: bool
) -> None:
    market = get_marketplace()
    lines = [
        "Тип: входящее сообщение" + (" (передано оператору)" if escalate else ""),
        f"Покупатель: {esc(mask_buyer(message.buyer_name))}",
        f"Заказ: {esc(order.number) if order else '—'}",
    ]
    if order is not None and order.items:
        lines.append(f"Товар: {esc(order.items[0].product.name)}")
        lines.append(f"Статус заказа: {ORDER_STATUS_LABELS[order.status]}")
    lines.append(f"Время: {fmt_dt(message.received_at)}")
    lines.append(f"\n💬 {esc(message.text[:1500])}")
    if message.problem_hint:
        lines.append(f"\n⚠️ Возможная причина: {esc(message.problem_hint)}")
    buttons: list[list[dict[str, Any]]] = []
    for label, text in suggestions:
        lines.append(f"\n{label} — готовый ответ:\n<code>{esc(text)}</code>")
        if len(text) <= 256:
            buttons.append([btn(f"📋 {label.split(' ', 1)[1]}", copy=text)])
    if market.supports("send_messages"):
        buttons.append([btn("✍️ Ответить", f"msg:reply:{message.id}")])
    row = [btn("✅ Обработано", f"msg:done:{message.id}"), btn("🧑‍💼 Оператору", f"msg:escalate:{message.id}")]
    buttons.append(row)
    if order is not None:
        buttons.append([btn("🛒 Открыть заказ", f"ord:open:{order.id}"), btn("⏸ Пауза автоматизации", f"ord:pause:{order.id}")])
        listing_id = order.items[0].listing_id if order.items else None
        if listing_id:
            buttons.append([btn("📝 Открыть объявление", f"lst:open:{listing_id}")])
    if not market.supports("send_messages"):
        lines.append("\n<i>PlayerOK без API: ответ отправляется вручную в чате сделки.</i>")
    await notify(
        session,
        "customer_message",
        f"Сообщение покупателя{f' · {order.number}' if order else ''}",
        "\n".join(lines),
        severity=Severity.WARNING if escalate else Severity.INFO,
        buttons=buttons,
        entity_type="customer_message",
        entity_id=message.id,
        permission="messages.manage",
    )


async def ignore_check(session: AsyncSession, message_id: int) -> None:
    message = await session.get(CustomerMessage, message_id)
    if message is None or message.status in (MessageStatus.HANDLED, MessageStatus.AUTO_REPLIED):
        return
    order = await session.get(Order, message.order_id) if message.order_id else None
    await hints.suggest(
        session,
        "ignore_text",
        "text",
        order,
        title=f"Сообщение {mask_buyer(message.buyer_name)} без ответа",
        context={"buyer": message.buyer_name or "покупатель"},
        dedupe_key=f"ignore:{message.id}",
    )


async def set_status(session: AsyncSession, message_id: int, status: MessageStatus, actor: Actor) -> CustomerMessage:
    message = await session.get(CustomerMessage, message_id, with_for_update=True)
    if message is None:
        raise NotFound("Сообщение не найдено")
    message.status = status
    message.handled_by = actor.label
    message.handled_at = utcnow()
    await audit(session, actor, f"message.{status.value}", entity_type="customer_message", entity_id=message.id)
    if status is MessageStatus.ESCALATED:
        await notify(
            session,
            "customer_message",
            "Сообщение передано оператору",
            f"{esc(mask_buyer(message.buyer_name))}: {esc(message.text[:500])}\nПередал: {esc(actor.label)}",
            severity=Severity.WARNING,
            buttons=[[btn("✅ Обработано", f"msg:done:{message.id}")]],
            entity_type="customer_message",
            entity_id=message.id,
            permission="messages.manage",
        )
    return message


async def record_outgoing(
    session: AsyncSession, *, text: str, order: Order | None, buyer_name: str | None, actor: Actor
) -> CustomerMessage:
    message = CustomerMessage(
        order_id=order.id if order else None,
        buyer_name=buyer_name or (order.buyer_name if order else None),
        direction=MessageDirection.OUTGOING,
        text=text.strip()[:4000],
        status=MessageStatus.HANDLED,
        source="manual",
        handled_by=actor.label,
        handled_at=utcnow(),
    )
    session.add(message)
    await session.flush()
    return message


def sentiment_for(rating: int | None, text: str) -> Sentiment:
    if rating is not None:
        return Sentiment.POSITIVE if rating >= 4 else Sentiment.NEUTRAL if rating == 3 else Sentiment.NEGATIVE
    lowered = text.lower()
    if any(w in lowered for w in ("плохо", "обман", "долго", "не работает", "ужас")):
        return Sentiment.NEGATIVE
    if any(w in lowered for w in ("спасибо", "отлично", "быстро", "супер", "рекоменд")):
        return Sentiment.POSITIVE
    return Sentiment.NEUTRAL


async def record_review(
    session: AsyncSession,
    *,
    order: Order | None,
    rating: int | None,
    text: str,
    actor: Actor,
    external_id: str | None = None,
    source: str = "manual",
) -> Review:
    if rating is not None and not 1 <= rating <= 5:
        raise DomainError("Оценка от 1 до 5")
    sentiment = sentiment_for(rating, text)
    review = Review(
        order_id=order.id if order else None,
        rating=rating,
        text=text.strip()[:4000],
        sentiment=sentiment,
        external_id=external_id,
        source=source,
    )
    session.add(review)
    if order is not None:
        order.review_received_at = utcnow()  # stops review reminders
    await session.flush()
    await audit(session, actor, "review.record", entity_type="review", entity_id=review.id, details={"rating": rating})
    await notify(
        session,
        "review",
        f"Отзыв {'⭐' * (rating or 0)}{f' · {order.number}' if order else ''}",
        esc(text[:1000]) or "(без текста)",
        severity=Severity.WARNING if sentiment is Sentiment.NEGATIVE else Severity.SUCCESS,
        buttons=[[btn("🛒 Открыть заказ", f"ord:open:{order.id}")]] if order else None,
        entity_type="review",
        entity_id=review.id,
    )
    await hints.suggest(session, "review_texts", sentiment.value, order, title="Ответ на отзыв", context={"rating": str(rating or "")})
    return review


async def list_messages(
    session: AsyncSession, *, status: str | None = None, page: int = 1, per_page: int = 10, query: str = ""
) -> tuple[list[CustomerMessage], int]:
    stmt = select(CustomerMessage).where(CustomerMessage.direction == MessageDirection.INCOMING)
    if status:
        stmt = stmt.where(CustomerMessage.status == MessageStatus(status))
    if query:
        like = f"%{query}%"
        stmt = stmt.where((CustomerMessage.text.ilike(like)) | (CustomerMessage.buyer_name.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(CustomerMessage.id.desc()).offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return list(rows), total


async def test_rules(session: AsyncSession, text: str, order: Order | None) -> dict[str, Any]:
    result = await match(session, text, order)
    return {"rule": result.rule.name if result.rule else None, "action": result.action, "reply": result.text, "reason": result.reason}
