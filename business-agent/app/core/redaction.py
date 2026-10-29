"""Удаление секретов из текстов перед записью в журналы."""
import logging
import re
from typing import Any

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"), "[bot-token]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b"), "[api-key]"),
    (re.compile(r"\b\d{3,8}:AA[A-Za-z0-9_-]{20,}\b"), "[api-token]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[private-key]"),
    (re.compile(r"\b(?:0x)?[0-9a-fA-F]{64}\b"), "[hex-secret]"),
    (re.compile(r"(?i)\b(password|пароль|passwd|secret|token|api[_-]?key|seed|mnemonic|сид)\b\s*[:=]\s*\S+"), r"\1=[redacted]"),
]
# 12/15/18/21/24 подряд идущих латинских слов в нижнем регистре — похоже на seed-фразу.
_SEED_RE = re.compile(r"\b(?:[a-z]{3,8}\s+){11,23}[a-z]{3,8}\b")
_SENSITIVE_KEYS = {"token", "api_key", "password", "secret", "seed", "mnemonic", "private_key", "authorization"}


def redact_text(text: str | None) -> str | None:
    if not text:
        return text
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return _SEED_RE.sub("[possible-seed-phrase]", text)


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if str(k).lower() in _SENSITIVE_KEYS else redact(v)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class RedactingFilter(logging.Filter):
    """Фильтр для stdlib logging: маскирует секреты в сообщениях и аргументах."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact(record.args)
            else:
                record.args = tuple(redact(a) for a in record.args)
        return True
