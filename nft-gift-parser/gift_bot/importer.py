"""Разбор TXT-файла от админа и фоновый парсинг подарков в базу."""
import asyncio
import logging
import re
import time
from itertools import islice
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from gift_parser.models import Gift
from gift_parser.parser import GiftParser, gift_url

from gift_bot.db import Database

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"(?:https?://)?t\.me/nft/([A-Za-z0-9]+)-(\d+)", re.I)
_SINGLE_RE = re.compile(r"([A-Za-z0-9]+)-(\d+)")
_RANGE_RE = re.compile(r"([A-Za-z0-9]+)[\s:]+(\d+)\s*(?:-|–|\s)\s*(\d+)")
_SLUG_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{4,32})\b")

SAVE_BATCH = 50
CHUNK = 200


@dataclass(slots=True)
class Target:
    """Что парсить: один номер, диапазон или вся коллекция (end=None)."""

    slug: str
    start: int = 1
    end: int | None = None
    owner: str | None = None  # username владельца из файла, без @


@dataclass(slots=True)
class ParsedFile:
    targets: list[Target] = field(default_factory=list)
    bad_lines: list[str] = field(default_factory=list)
    duplicates: int = 0  # точные повторы «юзернейм + ссылка», пропущены


def parse_targets(text: str) -> ParsedFile:
    """Строки файла:
        @username - https://t.me/nft/PlushPepe-1   (владелец берётся из файла)
        https://t.me/nft/PlushPepe-1   (можно несколько ссылок в строке)
        PlushPepe-1
        PlushPepe 1 500  /  PlushPepe 1-500
        PlushPepe                      (вся коллекция)
    Пустые строки и строки с # пропускаются.
    """
    result = ParsedFile()
    seen: set[tuple[str, int, int | None, str | None]] = set()

    def add(t: Target) -> None:
        """Точный повтор «юзернейм + ссылка» пропускаем; другой NFT того же юзера — нет."""
        key = (t.slug.lower(), t.start, t.end, t.owner.lower() if t.owner else None)
        if key in seen:
            result.duplicates += 1
            return
        seen.add(key)
        result.targets.append(t)

    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        links = _LINK_RE.findall(line)
        if links:
            user = _USERNAME_RE.search(_LINK_RE.sub(" ", line))
            for slug, num in links:
                add(Target(slug, int(num), int(num), user.group(1) if user else None))
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
    skipped: int = 0        # точные повторы: в файле и уже записанные в базе
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
                saved = db.save_gifts(buffer)
                self.found += saved
                self.skipped += len(buffer) - saved
                buffer.clear()

        def keep(gift: Gift) -> None:
            buffer.append(gift)
            if len(buffer) >= SAVE_BATCH:
                flush()

        try:
            # Целые коллекции: размер узнаём со страницы первого подарка.
            ranges: list[tuple[str, int, int]] = []
            for t in self.targets:
                if t.owner and t.end == t.start:
                    # «@user - ссылка»: всё нужное есть в файле, страницу не запрашиваем.
                    self.total += 1
                    self.done += 1
                    keep(Gift(slug=t.slug, number=t.start, url=gift_url(t.slug, t.start),
                              owner_name=f"@{t.owner}", owner_link=f"https://t.me/{t.owner}"))
                    continue
                if t.end is not None:
                    ranges.append((t.slug, t.start, t.end))
                    continue
                if self.cancelled:
                    break
                self.current = t.slug
                self.total += 1
                first = await parser.get_gift(t.slug, t.start)
                self.done += 1
                if first is None:
                    logger.warning("Коллекция %s не найдена", t.slug)
                    continue
                keep(first)
                end = first.total or first.issued or t.start
                if end > t.start:
                    ranges.append((t.slug, t.start + 1, end))
            self.total += sum(b - a + 1 for _, a, b in ranges)

            # Все номера одним потоком, кусками: параллельно внутри куска,
            # без десятков тысяч задач разом, и «Остановить» срабатывает быстро.
            refs = ((slug, n) for slug, a, b in ranges for n in range(a, b + 1))
            while not self.cancelled:
                chunk = list(islice(refs, CHUNK))
                if not chunk:
                    break
                self.current = chunk[-1][0]
                async for gift in parser.get_many(chunk):
                    keep(gift)
                self.done += len(chunk)
                if time.monotonic() - last_report > 5:
                    last_report = time.monotonic()
                    flush()
                    await on_progress(self)
        finally:
            flush()
            self.finished = True
