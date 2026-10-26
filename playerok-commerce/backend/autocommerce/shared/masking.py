"""Keep sensitive data out of logs, audit records and public payloads."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEYS = re.compile(
    r"(token|secret|password|passwd|authorization|signature|api[_-]?key|cookie|session|"
    r"client_secret|credential|pin|code_value|redeem|card_number|totp)",
    re.IGNORECASE,
)
_BOT_TOKEN_RE = re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,}")
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_KEY_PARAM_RE = re.compile(r"((?:key|token|api_key|client_secret)=)[^&\s\"']+", re.IGNORECASE)


def mask_secret(value: str | None, keep: int = 4) -> str:
    """``abcdef123456`` -> ``abcd…3456``; short values are fully hidden."""
    if not value:
        return ""
    if len(value) <= keep * 2 + 2:
        return "•" * min(len(value), 8)
    return f"{value[:keep]}…{value[-keep:]}"


def mask_code(code: str) -> str:
    """Digital product code shown in lists: only the last 4 characters."""
    clean = code.strip()
    if len(clean) <= 4:
        return "•" * len(clean)
    return "•••• " + clean[-4:]


def scrub_text(text: str) -> str:
    text = _BOT_TOKEN_RE.sub("<bot-token>", text)
    text = _BEARER_RE.sub(r"\1***", text)
    return _KEY_PARAM_RE.sub(r"\1***", text)


def scrub(data: Any, depth: int = 0) -> Any:
    """Recursively replace values of sensitive keys and token-like strings."""
    if depth > 8:
        return "…"
    if isinstance(data, dict):
        return {k: ("***" if isinstance(k, str) and _SENSITIVE_KEYS.search(k) else scrub(v, depth + 1)) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [scrub(v, depth + 1) for v in list(data)[:100]]
    if isinstance(data, str):
        return scrub_text(data)
    return data


def mask_buyer(name: str | None) -> str:
    """Public nickname for notifications: kept as is (it is public on the
    marketplace), trimmed to a sane length."""
    if not name:
        return "—"
    name = name.strip()
    return name if len(name) <= 32 else name[:31] + "…"
