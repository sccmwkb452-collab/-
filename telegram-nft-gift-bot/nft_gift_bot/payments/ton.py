"""TON amounts, invoice identifiers and wallet payment links."""

from __future__ import annotations

import secrets
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from urllib.parse import quote

NANO_IN_TON = 10**9
MEMO_PREFIX = "NFT-"


def ton_to_nano(amount: Decimal | str | int) -> int:
    try:
        value = Decimal(str(amount))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid TON amount: {amount!r}") from exc
    if value <= 0:
        raise ValueError("TON amount must be positive")
    nano = value * NANO_IN_TON
    if nano != nano.to_integral_value():
        raise ValueError("TON amount supports at most 9 decimal places")
    return int(nano)


def format_ton(nano: int) -> str:
    value = (Decimal(nano) / NANO_IN_TON).quantize(Decimal("0.000000001"), rounding=ROUND_DOWN).normalize()
    return f"{value:f}"


def new_memo() -> str:
    """Unguessable invoice ID the payer must put into the transfer comment."""
    return MEMO_PREFIX + secrets.token_hex(6).upper()


def ton_transfer_link(address: str, amount_nano: int, memo: str) -> str:
    """ton:// deep link (TON Connect-compatible wallets: Tonkeeper, MyTonWallet, Telegram Wallet)."""
    return f"ton://transfer/{address}?amount={amount_nano}&text={quote(memo)}"


def tonkeeper_link(address: str, amount_nano: int, memo: str) -> str:
    """HTTPS universal link; usable as an inline button URL (Telegram rejects ton:// in buttons)."""
    return f"https://app.tonkeeper.com/transfer/{address}?amount={amount_nano}&text={quote(memo)}"
