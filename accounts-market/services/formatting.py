"""Formatting helpers shared by messages and banners."""

from __future__ import annotations

import html
from datetime import datetime, timezone

NBSP = " "


def money(kopecks: int) -> str:
    sign = "-" if kopecks < 0 else ""
    rub, kop = divmod(abs(kopecks), 100)
    whole = f"{rub:,}".replace(",", NBSP)
    if kop:
        return f"{sign}{whole},{kop:02d}{NBSP}₽"
    return f"{sign}{whole}{NBSP}₽"


def signed_money(kopecks: int) -> str:
    return ("+" if kopecks > 0 else "") + money(kopecks)


def parse_rubles(text: str) -> int | None:
    """'1 490' / '1490,50' / '1490₽' -> kopecks. None if not a positive amount."""
    cleaned = text.strip().replace(" ", "").replace(NBSP, "").rstrip("₽").replace(",", ".")
    if not cleaned or cleaned.count(".") > 1:
        return None
    whole, _, frac = cleaned.partition(".")
    if not whole.isdigit() or (frac and (not frac.isdigit() or len(frac) > 2)):
        return None
    value = int(whole) * 100 + (int(frac.ljust(2, "0")) if frac else 0)
    return value if value > 0 else None


def parse_signed_rubles(text: str) -> int | None:
    text = text.strip()
    sign = 1
    if text[:1] in "+-":
        sign = -1 if text[0] == "-" else 1
        text = text[1:]
    value = parse_rubles(text)
    return None if value is None else sign * value


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def date(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y")


def dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def plural(n: int, one: str, few: str, many: str) -> str:
    n100, n10 = n % 100, n % 10
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many
