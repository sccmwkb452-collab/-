from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().display_timezone)


def to_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(local_tz())


def fmt_dt(value: datetime | None, with_seconds: bool = False) -> str:
    local = to_local(value)
    if local is None:
        return "—"
    return local.strftime("%d.%m.%Y %H:%M:%S" if with_seconds else "%d.%m.%Y %H:%M")


def ago(value: datetime | None) -> str:
    """«5 мин назад» for status lines."""
    if value is None:
        return "никогда"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    seconds = int((utcnow() - value).total_seconds())
    if seconds < 60:
        return "только что"
    if seconds < 3600:
        return f"{seconds // 60} мин назад"
    if seconds < 86400:
        return f"{seconds // 3600} ч назад"
    return f"{seconds // 86400} дн назад"


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    tz = local_tz()
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def local_today() -> date:
    return utcnow().astimezone(local_tz()).date()
