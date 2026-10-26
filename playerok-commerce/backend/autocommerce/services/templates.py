"""Safe message templates with ``{variable}`` placeholders.

Only ``{name}`` (letters, digits, underscore) is substituted — no attribute or
index access, so a template typed by an operator cannot reach internals.
Unknown placeholders stay as they are, which makes mistakes visible in the
preview instead of silently disappearing.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]{0,40})\}")

VARIABLES: dict[str, str] = {
    "buyer": "имя покупателя на PlayerOK",
    "order_number": "номер заказа",
    "product": "название товара",
    "quantity": "количество",
    "price": "цена заказа",
    "status": "текущий статус заказа",
    "delivery_time": "срок выдачи",
    "instructions": "инструкция по активации",
    "region": "регион товара",
    "availability": "наличие товара",
    "next_steps": "что будет дальше",
    "shop": "название магазина",
    "rating": "оценка из отзыва",
}

SAMPLE: dict[str, str] = {
    "buyer": "player_2026",
    "order_number": "PO-000123",
    "product": "Telegram Stars — 1 000 ⭐",
    "quantity": "1",
    "price": "1 590 ₽",
    "status": "📦 Готов к выдаче",
    "delivery_time": "до 30 минут",
    "instructions": "Stars поступят на ваш аккаунт Telegram по username.",
    "region": "любой",
    "availability": "в наличии",
    "next_steps": "Мы выдадим товар и пришлём сообщение.",
    "shop": "Мой магазин",
    "rating": "5",
}

# Phrases that claim the order is done. A reply containing them is allowed
# only when the order really is delivered or completed.
_COMPLETION_CLAIMS = re.compile(r"(выполнен|выдан|отправил|отправлен|доставлен|зачислен|готово|получите\s+код)", re.IGNORECASE)


def render(template: str, context: dict[str, Any]) -> str:
    def sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in context and context[key] is not None:
            return str(context[key])
        return match.group(0)

    return _PLACEHOLDER.sub(sub, template or "").strip()


def unknown_placeholders(template: str) -> list[str]:
    return sorted({m.group(1) for m in _PLACEHOLDER.finditer(template or "") if m.group(1) not in VARIABLES})


def claims_completion(text: str) -> bool:
    return bool(_COMPLETION_CLAIMS.search(text or ""))


def validate_template(template: str, *, max_length: int = 2000) -> list[str]:
    problems = []
    if len(template) > max_length:
        problems.append(f"Текст длиннее {max_length} символов")
    unknown = unknown_placeholders(template)
    if unknown:
        problems.append("Неизвестные переменные: " + ", ".join("{" + u + "}" for u in unknown))
    return problems
