"""Exact money arithmetic. Floats are never accepted for amounts."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal(100)


def to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("float is not allowed for money values")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip().replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid money value: {value!r}") from exc


def money(value: Decimal | int | str) -> Decimal:
    """Round to cents using commercial rounding."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    """Round up to a price step (1 ₽, 5 ₽, 0.01 ₽): a minimum price is never rounded down."""
    if step <= 0:
        return value.quantize(CENT, rounding=ROUND_CEILING)
    units = (value / step).to_integral_value(rounding=ROUND_CEILING)
    return (units * step).quantize(CENT, rounding=ROUND_HALF_UP)


def percent_of(amount: Decimal, percent: Decimal) -> Decimal:
    return money(amount * percent / HUNDRED)


def pct(value: Decimal | int | str) -> Decimal:
    """Percent value with 4 decimals (12.5 -> Decimal('12.5000'))."""
    return to_decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def fmt_money(amount: Decimal | None, currency: str = "RUB") -> str:
    """Human formatting: 1 234,50 ₽."""
    if amount is None:
        return "—"
    sign = "-" if amount < 0 else ""
    q = money(abs(amount))
    whole, frac = f"{q:.2f}".split(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    text = " ".join(groups)
    if frac != "00":
        text += "," + frac
    symbol = {"RUB": "₽", "USD": "$", "EUR": "€", "TON": "TON", "USDT": "USDT"}.get(currency, currency)
    return f"{sign}{text} {symbol}"


def fmt_pct(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}".replace(".", ",") + " %"
