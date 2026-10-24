"""How an order's item is named: Stars or a Telegram Premium subscription."""

from __future__ import annotations

PREMIUM_MONTHS = (3, 6, 12)
# What giftPremiumSubscription takes from the bot's Stars balance.
PREMIUM_GIFT_STARS = {3: 1000, 6: 1500, 12: 2500}


def months_ru(months: int) -> str:
    if months % 10 == 1 and months % 100 != 11:
        word = "месяц"
    elif months % 10 in (2, 3, 4) and months % 100 not in (12, 13, 14):
        word = "месяца"
    else:
        word = "месяцев"
    return f"{months} {word}"


def _stars(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def item_title(stars: int, premium_months: int | None) -> str:
    """«500 Stars» or «Telegram Premium на 3 месяца»."""
    if premium_months:
        return f"Telegram Premium на {months_ru(premium_months)}"
    return f"{_stars(stars)} Stars"


def item_line(stars: int, premium_months: int | None) -> str:
    """With the emoji for messages: «⭐️ 500 Stars» or «💎 Telegram Premium на 3 месяца»."""
    return ("💎 " if premium_months else "⭐️ ") + item_title(stars, premium_months)
