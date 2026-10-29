"""ИИ-агент диалога: получает решение модели и проверяет его кодом."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.ai.llm import LLMClient
from app.ai.prompts import INITIAL_MESSAGE_SYSTEM
from app.ai.schemas import DIALOGUE_DECISION_SCHEMA, INITIAL_MESSAGE_SCHEMA, STICKER_MOODS
from app.ai.state import DealState, Stage, normalize_currency
from app.ai.validation import (
    check_outgoing_text,
    currency_mentioned,
    detect_opt_out,
    extract_numbers,
    find_bot_mentions,
    price_mentioned,
)

logger = logging.getLogger(__name__)

MAX_ATTRS = 20
MAX_LIST_ITEMS = 15


@dataclass
class AgentResult:
    reply_text: str | None
    sticker_mood: str
    state: DealState
    opt_out: bool
    handoff: bool
    handoff_reason: str | None
    ready_for_deal: bool
    owner_note: str | None
    intent: str
    rejected_updates: list[str] = field(default_factory=list)
    reply_problems: list[str] = field(default_factory=list)


def apply_decision(
    decision: dict[str, Any],
    state: DealState,
    *,
    transcript_texts: list[str],
    latest_contact_text: str,
    allowed_bot_usernames: set[str],
    deal_created: bool,
    deal_paid: bool,
) -> AgentResult:
    """Применяет решение модели к состоянию с проверками. Чистая функция — легко тестировать."""
    new = state.model_copy(deep=True)
    rejected: list[str] = []
    upd = decision.get("state_update") or {}
    reply = (decision.get("reply_text") or "").strip() or None
    evidence = transcript_texts + ([reply] if reply else [])

    if upd.get("conversation_stage") in {s.value for s in Stage}:
        new.conversation_stage = Stage(upd["conversation_stage"])
    if upd.get("counterparty_role") in ("seller", "buyer"):
        new.counterparty_role = upd["counterparty_role"]
    for key in ("product_type", "item_description", "payment_method"):
        if upd.get(key):
            setattr(new, key, str(upd[key])[:500])
    for attr in (upd.get("item_attributes") or [])[:MAX_ATTRS]:
        name, value = str(attr.get("name", ""))[:64], str(attr.get("value", ""))[:200]
        if name and value:
            new.item_attributes[name] = value
    if isinstance(upd.get("quantity"), int):
        if upd["quantity"] > 0 and any(upd["quantity"] in {int(n) for n in extract_numbers(t) if n == int(n)} for t in evidence):
            new.quantity = upd["quantity"]
        elif upd["quantity"] == 1:
            new.quantity = 1  # «один подарок» часто без цифры
        else:
            rejected.append(f"quantity={upd['quantity']} не найдено в переписке")

    # Цены принимаются только если число реально прозвучало (защита от выдуманных цен).
    for key in ("seller_price", "buyer_target_price", "agreed_price"):
        value = upd.get(key)
        if value is None:
            continue
        if price_mentioned(value, evidence):
            setattr(new, key, str(value))
        else:
            rejected.append(f"{key}={value} не найдено в переписке")

    if upd.get("currency"):
        code = normalize_currency(upd["currency"])
        if code and currency_mentioned(code, evidence):
            new.currency = code
        else:
            rejected.append(f"currency={upd['currency']} не найдено в переписке")

    new.objections = (new.objections + [str(x)[:300] for x in upd.get("new_objections") or []])[-MAX_LIST_ITEMS:]
    new.agreements = (new.agreements + [str(x)[:300] for x in upd.get("new_agreements") or []])[-MAX_LIST_ITEMS:]
    if decision.get("interest_level"):
        new.interest_level = decision["interest_level"]

    # Посторонние боты в сообщении собеседника — фиксируем и никогда не используем.
    foreign = find_bot_mentions(latest_contact_text) - allowed_bot_usernames
    for bot in sorted(foreign):
        tag = "@" + bot
        if tag not in new.suspicious_links:
            new.suspicious_links.append(tag)

    opt_out = bool(decision.get("opt_out")) or detect_opt_out(latest_contact_text)
    handoff = bool(decision.get("handoff_required"))
    handoff_reason = decision.get("handoff_reason")

    problems: list[str] = []
    if reply:
        check = check_outgoing_text(
            reply, allowed_bot_usernames=allowed_bot_usernames, deal_created=deal_created, deal_paid=deal_paid
        )
        if not check.ok:
            problems = check.problems
            reply = None
            handoff = True
            handoff_reason = "Ответ ИИ не прошёл проверку: " + "; ".join(problems)

    if foreign and not handoff:
        handoff = True
        handoff_reason = "Собеседник предлагает другого бота: " + ", ".join("@" + b for b in sorted(foreign))
        # Ответ всё равно можно отправить: агент по правилам откажется от чужого бота.

    if opt_out:
        new.conversation_stage = Stage.DECLINED

    ready = bool(decision.get("ready_for_deal")) and all(
        [new.agreed_price, new.currency, new.quantity, new.item_description or new.item_attributes]
    )
    mood = decision.get("send_sticker_mood") if decision.get("send_sticker_mood") in STICKER_MOODS else "none"
    if handoff:
        new.requires_human_review = True
        new.human_review_reason = handoff_reason
        mood = "none"
    return AgentResult(
        reply_text=reply,
        sticker_mood=mood,
        state=new,
        opt_out=opt_out,
        handoff=handoff,
        handoff_reason=handoff_reason,
        ready_for_deal=ready,
        owner_note=decision.get("owner_note"),
        intent=decision.get("intent") or "other",
        rejected_updates=rejected,
        reply_problems=problems,
    )


class DialogueAgent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def decide(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        state: DealState,
        transcript_texts: list[str],
        latest_contact_text: str,
        allowed_bot_usernames: set[str],
        deal_created: bool,
        deal_paid: bool,
        effort: str | None = None,
    ) -> AgentResult:
        decision = await self.llm.generate_json(
            system=system, content=content, schema=DIALOGUE_DECISION_SCHEMA, effort=effort
        )
        result = apply_decision(
            decision,
            state,
            transcript_texts=transcript_texts,
            latest_contact_text=latest_contact_text,
            allowed_bot_usernames=allowed_bot_usernames,
            deal_created=deal_created,
            deal_paid=deal_paid,
        )
        if result.rejected_updates:
            logger.info("Отклонены обновления состояния: %s", result.rejected_updates)
        return result


def _profile_strings(profile: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for v in profile.values():
        if isinstance(v, dict):
            out.extend(_profile_strings(v))
        elif isinstance(v, list):
            out.extend(str(x) for x in v)
        elif v is not None:
            out.append(str(v))
    return out


async def prepare_initial_message(
    llm: LLMClient | None,
    template_text: str,
    profile: dict[str, Any],
    *,
    allow_adaptation: bool,
    allowed_bot_usernames: set[str],
) -> tuple[str, bool]:
    """Возвращает (текст, адаптирован_ли). При любой сомнительной адаптации — исходный шаблон."""
    if not allow_adaptation or llm is None or not profile:
        return template_text, False
    try:
        data = await llm.generate_json(
            system=INITIAL_MESSAGE_SYSTEM,
            content=[
                {
                    "type": "text",
                    "text": f"<template>\n{template_text}\n</template>\n\n<contact_profile>\n"
                    + json.dumps(profile, ensure_ascii=False)
                    + "\n</contact_profile>",
                }
            ],
            schema=INITIAL_MESSAGE_SCHEMA,
            effort="low",
        )
    except Exception as exc:  # noqa: BLE001 — адаптация не критична, шаблон надёжнее
        logger.warning("Не удалось адаптировать первое сообщение: %s", exc)
        return template_text, False
    text = (data.get("text") or "").strip()
    allowed_sources = [template_text, *_profile_strings(profile)]
    allowed_numbers = set().union(*(extract_numbers(s) for s in allowed_sources))
    if not text or not extract_numbers(text) <= allowed_numbers:
        return template_text, False
    check = check_outgoing_text(text, allowed_bot_usernames=allowed_bot_usernames, deal_created=False, deal_paid=False,
                                allow_links="http" in template_text or "t.me" in template_text)
    if not check.ok:
        return template_text, False
    return text, True
