from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_local(value: datetime, tz_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(ZoneInfo(tz_name))


def fmt_local(value: datetime | None, tz_name: str, pattern: str = "%d.%m.%Y %H:%M") -> str:
    if value is None:
        return "—"
    return to_local(value, tz_name).strftime(pattern)
