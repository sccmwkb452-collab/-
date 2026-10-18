"""Telegram-бот поверх парсера.

Запуск:
    BOT_TOKEN=123:ABC python bot.py

Команды в чате:
    PlushPepe-1 или https://t.me/nft/PlushPepe-1   — карточка подарка
    PlushPepe 1 100                                 — CSV-файл с номерами 1..100
"""
import asyncio
import csv
import io
import logging
import os
import re

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, Message
from aiogram.client.default import DefaultBotProperties

from gift_parser.models import CSV_FIELDS, Gift
from gift_parser.parser import GiftParser, parse_gift_ref

MAX_RANGE = 500
RANGE_RE = re.compile(r"^([A-Za-z0-9]+)\s+(\d+)\s+(\d+)$")

dp = Dispatcher()
parser = GiftParser(concurrency=5)


def esc(s: str | None) -> str:
    return (s or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_attr(attr) -> str:
    if not attr:
        return "—"
    return esc(attr.name) + (f" <i>({attr.rarity:g}%)</i>" if attr.rarity is not None else "")


def gift_card(g: Gift) -> str:
    owner = esc(g.owner_name)
    if g.owner_link:
        owner = f'<a href="{esc(g.owner_link)}">{owner}</a>'
    lines = [
        f'🎁 <b><a href="{g.url}">{esc(g.title or f"{g.slug} #{g.number}")}</a></b>',
        f"Модель: {fmt_attr(g.model)}",
        f"Фон: {fmt_attr(g.backdrop)}",
        f"Символ: {fmt_attr(g.symbol)}",
        f"Владелец: {owner}",
    ]
    if g.total:
        lines.append(f"Выпущено: {g.issued}/{g.total}")
    return "\n".join(lines)


@dp.message(CommandStart())
async def start(m: Message) -> None:
    await m.answer(
        "Пришли ссылку на NFT-подарок, например <code>https://t.me/nft/PlushPepe-1</code> "
        "или <code>PlushPepe-1</code>.\n\n"
        f"Диапазон в CSV: <code>PlushPepe 1 100</code> (до {MAX_RANGE} шт. за раз)."
    )


@dp.message(F.text.regexp(RANGE_RE))
async def collection_range(m: Message) -> None:
    slug, a, b = RANGE_RE.match(m.text.strip()).groups()
    start, end = sorted((int(a), int(b)))
    if end - start + 1 > MAX_RANGE:
        await m.answer(f"Слишком большой диапазон, максимум {MAX_RANGE}.")
        return
    status = await m.answer(f"⏳ Парсю {slug} #{start}–{end}…")
    gifts = [g async for g in parser.get_many((slug, n) for n in range(start, end + 1))]
    if not gifts:
        await status.edit_text("Ничего не найдено. Проверь название коллекции.")
        return
    gifts.sort(key=lambda g: g.number)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerows(g.to_flat_dict() for g in gifts)
    await m.answer_document(
        BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=f"{slug}_{start}-{end}.csv"),
        caption=f"Найдено {len(gifts)} из {end - start + 1}",
    )
    await status.delete()


@dp.message(F.text)
async def single(m: Message) -> None:
    try:
        slug, number = parse_gift_ref(m.text)
    except ValueError:
        await m.answer("Не понял. Пример: <code>PlushPepe-1</code> или <code>PlushPepe 1 100</code>")
        return
    gift = await parser.get_gift(slug, number)
    if not gift:
        await m.answer("Подарок не найден.")
        return
    if gift.image:
        await m.answer_photo(gift.image, caption=gift_card(gift))
    else:
        await m.answer(gift_card(gift), disable_web_page_preview=True)


async def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Укажи токен: BOT_TOKEN=... python bot.py")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    async with parser:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
