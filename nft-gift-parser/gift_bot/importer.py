"""Разбор TXT-файла от админа и фоновый парсинг подарков в базу."""
import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from gift_parser.models import Gift
from gift_parser.parser import GiftParser

from gift_bot.db import Database

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"(?:https?://)?t\.me/nft/([A-Za-z0-9]+)-(\d+)", re.I)
_SINGLE_RE = re.compile(r"([A-Za-z0-9]+)-(\d+)")
_RANGE_RE = re.compile(r"([A-Za-z0-9]+)[\s:]+(\d+)\s*(?:-|–|\s)\s*(\d+)")
_SLUG_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")

SAVE_BATCH = 50


@dataclass(slots=True)
class Target:
    """Что парсить: один номер, диапазон или вся коллекция (end=None)."""

    slug: str
    start: int = 1
    end: int | None = None


@dataclass(slots=True)
class ParsedFile:
    targets: list[Target] = field(default_factory=list)
    bad_lines: list[str] = field(default_factory=list)


def parse_targets(text: str) -> ParsedFile:
    """Строки файла:
        https://t.me/nft/PlushPepe-1   (можно несколько ссылок в строке)
        PlushPepe-1
        PlushPepe 1 500  /  PlushPepe 1-500
        PlushPepe                      (вся коллекция)
    Пустые строки и строки с # пропускаются.
    """
    result = ParsedFile()
    seen: set[tuple[str, int, int | None]] = set()

    def add(t: Target) -> None:
        key = (t.slug.lower(), t.start, t.end)
        if key not in seen:
            seen.add(key)
            result.targets.append(t)

    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        links = _LINK_RE.findall(line)
        if links:
            for slug, num in links:
                add(Target(slug, int(num), int(num)))
        elif m := _RANGE_RE.fullmatch(line):
            a, b = sorted((int(m.group(2)), int(m.group(3))))
            add(Target(m.group(1), a, b))
        elif m := _SINGLE_RE.fullmatch(line):
            add(Target(m.group(1), int(m.group(2)), int(m.group(2))))
        elif _SLUG_RE.fullmatch(line):
            add(Target(line))
        else:
            result.bad_lines.append(line)
    return result


@dataclass
class ImportJob:
    targets: list[Target]
    total: int = 0          # сколько номеров всего (известно после первых запросов)
    done: int = 0           # сколько номеров обработано
    found: int = 0          # сколько подарков сохранено
    started_at: float = field(default_factory=time.monotonic)
    cancelled: bool = False
    finished: bool = False
    current: str = ""

    async def run(
        self, db: Database, parser: GiftParser, on_progress: Callable[["ImportJob"], Awaitable[None]]
    ) -> None:
        buffer: list[Gift] = []
        last_report = 0.0

        def flush() -> None:
            if buffer:
                db.save_gifts(buffer)
                self.found += len(buffer)
                buffer.clear()

        try:
            for t in self.targets:
                if self.cancelled:
                    break
                self.current = t.slug
                start, end = t.start, t.end
                if end is None:
                    self.total += 1
                    first = await parser.get_gift(t.slug, start)
                    self.done += 1
                    if first is None:
                        logger.warning("Коллекция %s не найдена", t.slug)
                        continue
                    buffer.append(first)
                    end = first.total or first.issued or start
                    start += 1
                self.total += max(0, end - start + 1)
                # Режем на куски, чтобы не создавать десятки тысяч задач разом
                # и чтобы «Остановить» срабатывало быстро.
                for chunk_start in range(start, end + 1, 200):
                    if self.cancelled:
                        break
                    chunk = range(chunk_start, min(chunk_start + 200, end + 1))
                    async for gift in parser.get_many((t.slug, n) for n in chunk):
                        buffer.append(gift)
                        if len(buffer) >= SAVE_BATCH:
                            flush()
                    self.done += len(chunk)
                    if time.monotonic() - last_report > 5:
                        last_report = time.monotonic()
                        flush()
                        await on_progress(self)
        finally:
            flush()
            self.finished = True
