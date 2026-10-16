from __future__ import annotations

import re
from dataclasses import dataclass

USERNAME_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")
ID_RE = re.compile(r"^\d{5,15}$")
LINK_RE = re.compile(r"^(?:https?://)?t\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?$")
NFT_LINK_RE = re.compile(r"^(?:https?://)?(?:t\.me|telegram\.me)/nft/([A-Za-z0-9_]{1,64}-\d{1,10})/?(?:\?.*)?$")


@dataclass(frozen=True)
class RecipientRef:
    username: str | None = None
    user_id: int | None = None

    @property
    def label(self) -> str:
        return f"@{self.username}" if self.username else f"ID {self.user_id}"


@dataclass(frozen=True)
class ResolvedRecipient:
    chat_id: int
    label: str
    verified: bool  # False when Telegram could not confirm the user exists for this bot


def parse_recipient(text: str) -> RecipientRef | None:
    value = text.strip()
    if ID_RE.match(value):
        return RecipientRef(user_id=int(value))
    match = USERNAME_RE.match(value) or LINK_RE.match(value)
    if match:
        username = match.group(1)
        if username.lower().endswith("bot"):
            return None  # bots cannot own gifts
        return RecipientRef(username=username)
    return None


def parse_nft_link(text: str) -> str | None:
    """Return the unique gift slug from a link like https://t.me/nft/PlushPepe-12."""
    match = NFT_LINK_RE.match(text.strip())
    return match.group(1) if match else None
