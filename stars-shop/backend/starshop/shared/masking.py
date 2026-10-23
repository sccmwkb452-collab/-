"""Helpers that keep sensitive data out of logs and public payloads."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEYS = re.compile(
    r"(token|secret|password|passwd|authorization|signature|api[_-]?key|init_?data|hash|cookie|session)",
    re.IGNORECASE,
)
_BOT_TOKEN_RE = re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,}")


def mask_value(value: str, keep: int = 4) -> str:
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "…" + "*" * 4


def scrub(data: Any, depth: int = 0) -> Any:
    """Recursively replace values of sensitive keys."""
    if depth > 6:
        return "…"
    if isinstance(data, dict):
        return {k: ("***" if isinstance(k, str) and _SENSITIVE_KEYS.search(k) else scrub(v, depth + 1)) for k, v in data.items()}
    if isinstance(data, list):
        return [scrub(v, depth + 1) for v in data[:50]]
    if isinstance(data, str):
        return _BOT_TOKEN_RE.sub("<bot-token>", data)
    return data


def mask_username(username: str | None) -> str:
    """``@durov`` -> ``@du***v`` for safe display of a recipient."""
    if not username:
        return "—"
    name = username.lstrip("@")
    if len(name) <= 3:
        return "@" + name[0] + "**"
    return "@" + name[:2] + "*" * min(3, len(name) - 3) + name[-1]
