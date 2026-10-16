"""Recognising a transfer request in free text.

Examples that parse:
    "передай Plush Pepe #12 @alice"
    "отправь подарок 3 пользователю @alice"
    "/transfer 3 123456789"
Parsing only *prepares* a transfer; execution always needs an explicit button confirmation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nft_gift_bot.gifts.recipient import RecipientRef, parse_recipient

_VERB_RE = re.compile(
    r"^\s*(?:/transfer(?:@\w+)?|передай|передать|отправь|отправить|подари|подарить|transfer|send)\b\s*",
    re.IGNORECASE,
)
_FILLER_RE = re.compile(r"\b(?:подарок|подарки|gift|nft|пользователю|юзеру|to|для|кому)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TransferIntent:
    gift_query: str
    recipient: RecipientRef


def parse_transfer_intent(text: str) -> TransferIntent | None:
    match = _VERB_RE.match(text)
    if not match:
        return None
    rest = text[match.end():].strip()
    tokens = rest.split()
    if len(tokens) < 2:
        return None
    recipient = parse_recipient(tokens[-1])
    if recipient is None:
        return None
    gift_query = _FILLER_RE.sub(" ", " ".join(tokens[:-1]))
    gift_query = re.sub(r"\s+", " ", gift_query).strip()
    if not gift_query:
        return None
    return TransferIntent(gift_query=gift_query, recipient=recipient)
