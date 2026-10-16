"""Message builder producing text + MessageEntity list.

Premium emoji are sent as ``custom_emoji`` entities over their Unicode
fallback character, which is what Telegram shows to users without Premium or
when the ID is not configured. Using entities (not HTML) means user-provided
strings never need escaping.
"""

from __future__ import annotations

from typing import Any

from aiogram.enums import MessageEntityType
from aiogram.types import MessageEntity

from nft_gift_bot.config.emoji import is_configured_id, resolve


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


class Rich:
    def __init__(self, emoji_overrides: dict[str, str] | None = None) -> None:
        self._overrides = emoji_overrides or {}
        self.text = ""
        self.entities: list[MessageEntity] = []

    def _span(self, value: str, entity_type: str, **extra: Any) -> Rich:
        if not value:
            return self
        offset = utf16_len(self.text)
        self.text += value
        self.entities.append(MessageEntity(type=entity_type, offset=offset, length=utf16_len(value), **extra))
        return self

    def t(self, value: object) -> Rich:
        self.text += str(value)
        return self

    def nl(self, count: int = 1) -> Rich:
        self.text += "\n" * count
        return self

    def b(self, value: object) -> Rich:
        return self._span(str(value), MessageEntityType.BOLD)

    def i(self, value: object) -> Rich:
        return self._span(str(value), MessageEntityType.ITALIC)

    def code(self, value: object) -> Rich:
        return self._span(str(value), MessageEntityType.CODE)

    def e(self, key: str) -> Rich:
        spec = resolve(key, self._overrides)
        if is_configured_id(spec.custom_id):
            return self._span(spec.fallback, MessageEntityType.CUSTOM_EMOJI, custom_emoji_id=spec.custom_id)
        return self.t(spec.fallback)

    def line(self, key: str, value: object = "") -> Rich:
        """Emoji-prefixed line: the single notification style used everywhere."""
        return self.e(key).t(" ").t(value).nl()

    def kwargs(self) -> dict[str, Any]:
        return {"text": self.text, "entities": self.entities or None, "parse_mode": None}
