"""Structured JSON logs with secret scrubbing (tokens, keys, codes)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from .config import get_settings
from .shared.masking import scrub

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            record.args = tuple(scrub(a) if isinstance(a, (str, dict, list)) else a for a in args)
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        if extra:
            data.update(scrub(extra))
        if record.exc_info:
            data["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging(service: str) -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ScrubFilter())
    if settings.log_json:
        handler.setFormatter(JsonFormatter(service))
    else:
        handler.setFormatter(logging.Formatter(f"%(asctime)s %(levelname)-7s [{service}] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    # httpx logs full request URLs; the Bot API URL contains the token.
    for noisy in ("httpx", "httpcore", "aiogram.event", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
