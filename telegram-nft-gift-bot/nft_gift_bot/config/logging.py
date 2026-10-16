"""Structured JSON logs with secret redaction."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable

_PATTERNS = [
    re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}"),  # bot tokens
    re.compile(r"gAAAAA[A-Za-z0-9_\-=]{20,}"),  # Fernet tokens
    re.compile(r"(?i)(api[_-]?key|token|password|secret)=([^&\s]+)"),
]
_STANDARD = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s and len(s) >= 6]

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        for pattern in _PATTERNS:
            text = pattern.sub(lambda m: (m.group(1) + "=***") if m.lastindex == 2 else "***", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = None
        for key, value in list(vars(record).items()):
            if key not in _STANDARD and isinstance(value, str):
                setattr(record, key, self.redact(value))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str, secrets: Iterable[str]) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter(secrets))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
