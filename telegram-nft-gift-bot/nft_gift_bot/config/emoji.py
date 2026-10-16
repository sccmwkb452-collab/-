"""Premium custom emoji configuration.

Every UI emoji has a Unicode fallback and an optional Telegram custom emoji ID.
The IDs below are DEMO placeholders: they are not real Telegram IDs and are
never sent to Telegram. Replace them with real IDs (admin command
``/set_emoji <key> <id>`` or the EMOJI_<KEY> env var) and verify with ``/check_emoji``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEMO_PREFIX = "DEMO_"


@dataclass(frozen=True)
class EmojiSpec:
    key: str
    fallback: str
    custom_id: str


_DEFAULTS: dict[str, tuple[str, str]] = {
    "brand": ("💎", "DEMO_BRAND"),
    "subscription": ("💎", "DEMO_SUBSCRIPTION"),
    "payment_ok": ("✅", "DEMO_PAYMENT_OK"),
    "payment": ("💳", "DEMO_PAYMENT"),
    "wallet": ("👛", "DEMO_WALLET"),
    "gift": ("🎁", "DEMO_GIFT"),
    "account": ("👤", "DEMO_ACCOUNT"),
    "security": ("🔐", "DEMO_SECURITY"),
    "error": ("❌", "DEMO_ERROR"),
    "warning": ("⚠️", "DEMO_WARNING"),
    "time": ("⏳", "DEMO_TIME"),
    "history": ("📜", "DEMO_HISTORY"),
    "settings": ("⚙️", "DEMO_SETTINGS"),
    "support": ("🆘", "DEMO_SUPPORT"),
    "admin": ("🛠", "DEMO_ADMIN"),
    "star": ("⭐", "DEMO_STAR"),
}

EMOJI_KEYS: tuple[str, ...] = tuple(_DEFAULTS)


def is_configured_id(custom_id: str | None) -> bool:
    """A usable custom emoji ID is a positive integer string (Telegram format)."""
    return bool(custom_id) and custom_id.isdigit() and int(custom_id) > 0


def resolve(key: str, overrides: dict[str, str] | None = None) -> EmojiSpec:
    if key not in _DEFAULTS:
        raise KeyError(f"Unknown emoji key: {key}")
    fallback, custom_id = _DEFAULTS[key]
    custom_id = os.environ.get(f"EMOJI_{key.upper()}", custom_id)
    if overrides and key in overrides:
        custom_id = overrides[key]
    return EmojiSpec(key=key, fallback=fallback, custom_id=custom_id)
