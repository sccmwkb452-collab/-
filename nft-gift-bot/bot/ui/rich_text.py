"""
Rich-text builder: объединяет HTML-разметку и Telegram Custom Emoji entities.

Telegram Bot API не позволяет одновременно передавать parse_mode и entities.
Этот модуль строит entities-список вручную, включая custom_emoji, bold, italic и пр.

Пример:
    rt = RichTextBuilder()
    rt.bold("NFT Gift Bot")
    rt.newline()
    rt.custom_emoji("diamond")   # 💎 или custom animated
    rt.text(" Ваш баланс: 0 подарков")
    text, entities = rt.build()
    await message.answer(text, entities=entities)
"""
from __future__ import annotations

from aiogram.types import MessageEntity

from config.emoji import EMOJI, EmojiConfig


class RichTextBuilder:
    """Накапливает текст и entities; собирает финальную пару (text, entities)."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._entities: list[MessageEntity] = []

    # ── position helpers ──────────────────────────────────────────────────────
    @property
    def _offset(self) -> int:
        return len("".join(self._parts).encode("utf-16-le")) // 2  # UTF-16 code units

    def _add_entity(self, entity_type: str, length_utf16: int, **kwargs) -> None:
        self._entities.append(
            MessageEntity(type=entity_type, offset=self._offset, length=length_utf16, **kwargs)
        )

    # ── unicode length ────────────────────────────────────────────────────────
    @staticmethod
    def _utf16_len(s: str) -> int:
        return len(s.encode("utf-16-le")) // 2

    # ── public API ────────────────────────────────────────────────────────────
    def text(self, s: str) -> "RichTextBuilder":
        self._parts.append(s)
        return self

    def newline(self, count: int = 1) -> "RichTextBuilder":
        self._parts.append("\n" * count)
        return self

    def bold(self, s: str) -> "RichTextBuilder":
        self._add_entity("bold", self._utf16_len(s))
        self._parts.append(s)
        return self

    def italic(self, s: str) -> "RichTextBuilder":
        self._add_entity("italic", self._utf16_len(s))
        self._parts.append(s)
        return self

    def code(self, s: str) -> "RichTextBuilder":
        self._add_entity("code", self._utf16_len(s))
        self._parts.append(s)
        return self

    def custom_emoji(self, key: str) -> "RichTextBuilder":
        """Вставляет emoji: custom animated если ID задан, иначе обычный символ."""
        cfg: EmojiConfig = EMOJI[key]
        char = cfg.char
        length = self._utf16_len(char)
        if cfg.custom_id:
            self._add_entity("custom_emoji", length, custom_emoji_id=cfg.custom_id)
        self._parts.append(char)
        return self

    def emoji(self, key: str) -> "RichTextBuilder":
        """Просто вставляет emoji-символ без entity (для тех мест, где не нужен custom)."""
        self._parts.append(EMOJI[key].char)
        return self

    def separator(self, char: str = "─", width: int = 28) -> "RichTextBuilder":
        self._parts.append(char * width)
        return self

    def build(self) -> tuple[str, list[MessageEntity]]:
        return "".join(self._parts), self._entities


def e(key: str) -> str:
    """Быстрый доступ к символу emoji по ключу."""
    return EMOJI[key].char
