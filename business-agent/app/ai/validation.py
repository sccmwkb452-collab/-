"""Проверки решений ИИ кодом — ИИ не может обойти их формулировкой.

- цены/валюты принимаются, только если реально прозвучали в переписке;
- исходящий текст не может ссылаться на посторонних ботов;
- исходящий текст не может утверждать, что сделка создана/оплачена, если это не так.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.ai.state import CURRENCY_ALIASES, normalize_currency, to_decimal

_NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:[  ]\d{3})+|\d+)(?:[.,](\d+))?(?:\s*(k|к|тыс))?", re.I)
_BOT_MENTION_RE = re.compile(r"(?:@|(?:https?://)?(?:t\.me|telegram\.me)/)([A-Za-z0-9_]{4,32})", re.I)
_LINK_RE = re.compile(r"https?://\S+|(?:t\.me|telegram\.me)/\S+", re.I)

OPT_OUT_PATTERNS = [
    r"\bне\s+пиши(те)?\b", r"\bне\s+беспоко", r"\bотстань", r"\bотпиш", r"\bудали(те)?\s+меня",
    r"\bне\s+интересно\b.*\bне\s+пиш", r"^\s*стоп\s*$", r"\bstop\b", r"\bunsubscribe\b", r"\bdon'?t\s+(text|message|write)\b",
    r"\bспам\b",
]
_OPT_OUT_RE = re.compile("|".join(OPT_OUT_PATTERNS), re.I | re.M)

# Утверждения о выполненных финансовых действиях.
_COMPLETION_CLAIMS = re.compile(
    r"(сделк[аи]\s+(уже\s+)?(создан|оформлен|открыт)|"
    r"(я\s+)?(уже\s+)?(оплатил|перевёл|перевел|отправил\s+(деньги|оплату|платёж|платеж))|"
    r"оплата\s+(уже\s+)?(прошла|отправлена|выполнена)|платёж\s+(прошёл|отправлен)|платеж\s+(прошел|отправлен)|"
    r"deal\s+(is\s+)?created|payment\s+(is\s+)?(sent|done|completed)|i\s+(have\s+)?paid)",
    re.I,
)


def extract_numbers(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for m in _NUMBER_RE.finditer(text or ""):
        whole = re.sub(r"[  ]", "", m.group(1))
        raw = whole + ("." + m.group(2) if m.group(2) else "")
        value = to_decimal(raw)
        if value is None:
            continue
        if m.group(3):
            value *= 1000
        found.add(value.normalize())
        # «1,5» и «1.5» уже покрыты; «1 000» — тоже.
    return found


def price_mentioned(value: str | None, texts: list[str]) -> bool:
    amount = to_decimal(value)
    if amount is None:
        return False
    target = amount.normalize()
    return any(target in extract_numbers(t) for t in texts)


def currency_mentioned(code: str | None, texts: list[str]) -> bool:
    code = normalize_currency(code)
    if not code:
        return False
    variants = {alias for alias, c in CURRENCY_ALIASES.items() if c == code} | {code.lower()}
    joined = " ".join(texts).lower()
    return any(v in joined for v in variants)


def detect_opt_out(text: str) -> bool:
    return bool(_OPT_OUT_RE.search(text or ""))


def find_bot_mentions(text: str) -> set[str]:
    """Упоминания аккаунтов, похожих на ботов (оканчиваются на bot)."""
    return {m.group(1).lower() for m in _BOT_MENTION_RE.finditer(text or "") if m.group(1).lower().endswith("bot")}


@dataclass
class ReplyCheck:
    ok: bool
    problems: list[str] = field(default_factory=list)


def check_outgoing_text(
    text: str,
    *,
    allowed_bot_usernames: set[str],
    deal_created: bool,
    deal_paid: bool,
    allow_links: bool = False,
) -> ReplyCheck:
    problems: list[str] = []
    if not text or not text.strip():
        problems.append("пустой текст")
    if len(text) > 4096:
        problems.append("текст длиннее 4096 символов")
    foreign = find_bot_mentions(text) - {u.lower() for u in allowed_bot_usernames}
    if foreign:
        problems.append("упоминание неразрешённых ботов: " + ", ".join(sorted("@" + f for f in foreign)))
    if not allow_links:
        for link in _LINK_RE.findall(text):
            m = _BOT_MENTION_RE.search(link)
            if not (m and m.group(1).lower() in allowed_bot_usernames):
                problems.append(f"посторонняя ссылка: {link}")
    claim = _COMPLETION_CLAIMS.search(text)
    if claim and not (deal_created or deal_paid):
        problems.append(f"утверждение о несуществующей сделке/оплате: «{claim.group(0)}»")
    return ReplyCheck(ok=not problems, problems=problems)
