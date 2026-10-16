from __future__ import annotations

import re
from dataclasses import dataclass

USERNAME_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")
ID_RE = re.compile(r"^\d{5,15}$")
LINK_RE = re.compile(r"^(?:https?://)?t\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?$")


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
