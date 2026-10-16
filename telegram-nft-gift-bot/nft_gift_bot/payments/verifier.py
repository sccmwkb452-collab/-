"""Matching on-chain incoming transfers to invoices.

A payment counts only if a transaction that actually landed on the receiver
wallet carries the invoice memo as its comment and at least the invoiced amount.
Anything the user sends to the bot (screenshots, hashes, "I paid") is ignored.
"""

from __future__ import annotations

from collections.abc import Container, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class IncomingTransfer:
    tx_hash: str
    sender: str
    value_nano: int
    comment: str
    utime: int


def find_payment_transfer(
    transfers: Iterable[IncomingTransfer],
    memo: str,
    min_amount_nano: int,
    used_hashes: Container[str] = frozenset(),
    not_before_utime: int = 0,
) -> IncomingTransfer | None:
    for transfer in transfers:
        if transfer.comment.strip() != memo:
            continue
        if transfer.value_nano < min_amount_nano:
            continue
        if transfer.tx_hash in used_hashes:
            continue
        if transfer.utime < not_before_utime:
            continue
        return transfer
    return None
