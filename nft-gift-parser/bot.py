"""Telegram-бот поверх парсера.

Запуск:
    BOT_TOKEN=123:ABC python bot.py

Команды в чате:
    PlushPepe-1 или https://t.me/nft/PlushPepe-1   — карточка подарка
    PlushPepe 1 100                                 — CSV-файл с номерами 1..100
    /gifts [поиск]                                  — новые коллекции подарков
    /lang ja                                        — язык бота и страниц (ru, en, ja, ko, zh, ar, …)
"""
import asyncio
import csv
import io
import logging
import os
import re

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, Message
from aiogram.client.default import DefaultBotProperties

from gift_parser.catalog import find, latest
from gift_parser.models import CSV_FIELDS, Gift
from gift_parser.parser import LANGUAGES, GiftParser, parse_gift_ref
from texts import DEFAULT, TEXTS, t

MAX_RANGE = 500
RANGE_RE = re.compile(r"^([A-Za-z0-9]+)\s+(\d+)\s+(\d+)$")

dp = Dispatcher()
parser = GiftParser(concurrency=5)
user_lang: dict[int, str] = {}


def lang_of(m: Message) -> str:
    """Выбранный через /lang язык, иначе язык Telegram пользователя."""
    if not m.from_user:
        return DEFAULT
    if m.from_user.id in user_lang:
        return user_lang[m.from_user.id]
    code = (m.from_user.language_code or "").split("-")[0].lower()
    return code if code in LANGUAGES else DEFAULT


def esc(s: str | None) -> str:
    return (s or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_attr(attr) -> str:
    if not attr:
        return "—"
    return esc(attr.name) + (f" <i>({attr.rarity:g}%)</i>" if attr.rarity is not None else "")


def gift_card(g: Gift, lang: str) -> str:
    owner = esc(g.owner_name)
    if g.owner_link:
        owner = f'<a href="{esc(g.owner_link)}">{owner}</a>'
    lines = [
        f'🎁 <b><a href="{g.url}">{esc(g.title or f"{g.slug} #{g.number}")}</a></b>',
        f"{t(lang, 'model')}: {fmt_attr(g.model)}",
        f"{t(lang, 'backdrop')}: {fmt_attr(g.backdrop)}",
        f"{t(lang, 'symbol')}: {fmt_attr(g.symbol)}",
        f"{t(lang, 'owner')}: {owner}",
    ]
    if g.total:
        lines.append(f"{t(lang, 'issued')}: {g.issued}/{g.total}")
    return "\n".join(lines)


@dp.message(CommandStart())
async def start(m: Message) -> None:
    await m.answer(t(lang_of(m), "start", max=MAX_RANGE))


@dp.message(Command("gifts"))
async def gifts(m: Message, command: CommandObject) -> None:
    lang = lang_of(m)
    items = find(command.args) if command.args else latest(20)
    if not items:
        await m.answer(t(lang, "no_collection"))
        return
    lines = [f'• <a href="https://t.me/nft/{s}-1">{esc(name)}</a> — <code>{s}</code>' for s, name in items[:50]]
    title = t(lang, "found" if command.args else "latest")
    await m.answer(f"<b>{title}:</b>\n" + "\n".join(lines), disable_web_page_preview=True)


@dp.message(Command("lang"))
async def set_lang(m: Message, command: CommandObject) -> None:
    code = (command.args or "").strip().lower()
    if code not in LANGUAGES:
        # Сначала языки с переведённым интерфейсом, остальные — только для страниц.
        codes = list(TEXTS) + [c for c in LANGUAGES if c not in TEXTS]
        options = "\n".join(f"<code>/lang {c}</code> {LANGUAGES[c]}" for c in codes)
        current = lang_of(m)
        await m.answer(t(current, "lang_now", lang=LANGUAGES[current]) + "\n\n" + options)
        return
    user_lang[m.from_user.id] = code
    await m.answer(t(code, "lang_set", lang=LANGUAGES[code]))


@dp.message(F.text.regexp(RANGE_RE))
async def collection_range(m: Message) -> None:
    lang = lang_of(m)
    slug, a, b = RANGE_RE.match(m.text.strip()).groups()
    start, end = sorted((int(a), int(b)))
    if end - start + 1 > MAX_RANGE:
        await m.answer(t(lang, "too_big", max=MAX_RANGE))
        return
    status = await m.answer(t(lang, "parsing", slug=slug, start=start, end=end))
    found = [g async for g in parser.get_many(((slug, n) for n in range(start, end + 1)), lang)]
    if not found:
        await status.edit_text(t(lang, "nothing"))
        return
    found.sort(key=lambda g: g.number)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    w.writerows(g.to_flat_dict() for g in found)
    await m.answer_document(
        BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=f"{slug}_{start}-{end}.csv"),
        caption=t(lang, "found_of", n=len(found), total=end - start + 1),
    )
    await status.delete()


@dp.message(F.text)
async def single(m: Message) -> None:
    lang = lang_of(m)
    try:
        slug, number = parse_gift_ref(m.text)
    except ValueError:
        await m.answer(t(lang, "not_understood"))
        return
    gift = await parser.get_gift(slug, number, lang)
    if not gift:
        await m.answer(t(lang, "not_found"))
        return
    if gift.image:
        await m.answer_photo(gift.image, caption=gift_card(gift, lang))
    else:
        await m.answer(gift_card(gift, lang), disable_web_page_preview=True)


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
