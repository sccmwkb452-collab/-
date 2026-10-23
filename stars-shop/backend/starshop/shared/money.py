"""Exact money arithmetic. Floats are never used for amounts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):  # pragma: no cover - defensive
        raise TypeError("float is not allowed for money values")
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid money value: {value!r}") from exc


def money(value: Decimal | int | str) -> Decimal:
    """Round to cents using commercial rounding."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, percent: Decimal) -> Decimal:
    return money(amount * percent / Decimal(100))


def fmt(amount: Decimal) -> str:
    """Canonical string form used in API payloads and provider requests."""
    return str(money(amount))
