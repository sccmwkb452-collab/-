"""CLI: python -m gift_parser ...

Примеры:
    python -m gift_parser PlushPepe-1
    python -m gift_parser https://t.me/nft/DurovsCap-42 --format json
    python -m gift_parser PlushPepe --from 1 --to 200 -o pepe.csv
    python -m gift_parser PlushPepe -o pepe.json          # вся коллекция
    python -m gift_parser PlushPepe --to 500 --model "Pumpkin" --max-rarity 1
    python -m gift_parser PlushPepe-1 --lang ja       # страница на японском
    python -m gift_parser --list                      # известные коллекции, новые сверху
    python -m gift_parser --check UFCStrike SnoopDogg # есть ли такие коллекции
    python -m gift_parser PlushPepe --to 1000 --owner-lang ko,ja -o asia.csv  # владельцы-корейцы и японцы
"""
import argparse
import asyncio
import csv
import json
import logging
import re
import sys

from gift_parser.catalog import COLLECTIONS, find
from gift_parser.models import CSV_FIELDS, Gift
from gift_parser.owner_lang import OWNER_LANGS
from gift_parser.parser import LANGUAGES, GiftParser, parse_gift_ref


def build_args() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gift_parser", description="Парсер NFT-подарков Telegram")
    p.add_argument("target", nargs="*",
                   help="Ссылки/номера подарков (PlushPepe-1) или название коллекции (PlushPepe)")
    p.add_argument("--from", dest="start", type=int, default=1, help="Начальный номер (по умолчанию 1)")
    p.add_argument("--to", dest="end", type=int, help="Конечный номер (по умолчанию — вся коллекция)")
    p.add_argument("-o", "--output", help="Файл .csv или .json (по умолчанию — вывод в консоль)")
    p.add_argument("--format", choices=["table", "json", "csv"], help="Формат вывода в консоль")
    p.add_argument("-c", "--concurrency", type=int, default=5, help="Параллельных запросов")
    p.add_argument("--delay", type=float, default=0.2, help="Пауза после запроса, с")
    p.add_argument("--proxy", help="HTTP-прокси, например http://user:pass@host:port")
    p.add_argument("--lang", default="en", choices=sorted(LANGUAGES), metavar="LANG",
                   help="Язык страниц: " + ", ".join(sorted(LANGUAGES)))
    p.add_argument("--list", nargs="?", const="", metavar="ПОИСК",
                   help="Показать известные коллекции (новые сверху), можно с поиском")
    p.add_argument("--check", action="store_true",
                   help="Проверить, что коллекции из target существуют, и показать их размер")
    p.add_argument("--model", help="Фильтр по модели (подстрока)")
    p.add_argument("--backdrop", help="Фильтр по фону (подстрока)")
    p.add_argument("--symbol", help="Фильтр по символу (подстрока)")
    p.add_argument("--owner-lang", type=lambda s: {c.strip().lower() for c in s.split(",") if c.strip()},
                   help="Владельцы по языку имени через запятую: " + ", ".join(OWNER_LANGS))
    p.add_argument("--max-rarity", type=float,
                   help="Оставить подарки, у которых хотя бы один атрибут реже N%%")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def matches(gift: Gift, args: argparse.Namespace) -> bool:
    for key in ("model", "backdrop", "symbol"):
        needle = getattr(args, key)
        attr = getattr(gift, key)
        if needle and not (attr and needle.lower() in attr.name.lower()):
            return False
    if args.owner_lang and gift.owner_lang not in args.owner_lang:
        return False
    if args.max_rarity is not None:
        rarities = [a.rarity for a in (gift.model, gift.backdrop, gift.symbol) if a and a.rarity is not None]
        if not any(r <= args.max_rarity for r in rarities):
            return False
    return True


def fmt_attr(attr) -> str:
    if not attr:
        return "—"
    return f"{attr.name} ({attr.rarity:g}%)" if attr.rarity is not None else attr.name


def print_table(gift: Gift) -> None:
    print(f"{gift.title or f'{gift.slug} #{gift.number}'}  {gift.url}")
    print(f"  Модель:   {fmt_attr(gift.model)}")
    print(f"  Фон:      {fmt_attr(gift.backdrop)}")
    print(f"  Символ:   {fmt_attr(gift.symbol)}")
    lang = f"  [{OWNER_LANGS[gift.owner_lang]}]" if gift.owner_lang in OWNER_LANGS else ""
    print(f"  Владелец: {gift.owner_name or '—'}" + (f"  ({gift.owner_link})" if gift.owner_link else "") + lang)
    if gift.total:
        print(f"  Выпущено: {gift.issued}/{gift.total}")
    print()


async def collect(args: argparse.Namespace):
    async with GiftParser(
        concurrency=args.concurrency, delay=args.delay, proxy=args.proxy, lang=args.lang
    ) as parser:
        refs, collections = [], []
        for t in args.target:
            if re.fullmatch(r"[A-Za-z0-9]+", t.strip()):
                collections.append(t.strip())
            else:
                refs.append(parse_gift_ref(t))

        async for gift in parser.get_many(refs):
            yield gift
        for slug in collections:
            async for gift in parser.get_collection(slug, args.start, args.end):
                yield gift


def print_collections(query: str) -> int:
    items = find(query) if query else COLLECTIONS
    for slug, name in items:
        print(f"{slug:<16} {name}")
    print(f"Всего: {len(items)}", file=sys.stderr)
    return 0 if items else 1


async def check(args: argparse.Namespace) -> int:
    async with GiftParser(concurrency=args.concurrency, delay=args.delay,
                          proxy=args.proxy, lang=args.lang) as parser:
        ok = 0
        for t in args.target:
            slug = t.strip().split("-")[0]
            gift = await parser.get_gift(slug, 1)
            if gift:
                ok += 1
                print(f"✓ {slug:<16} {gift.title or ''}  всего: {gift.total or '?'}")
            else:
                print(f"✗ {slug:<16} не найдена")
    return 0 if ok == len(args.target) else 1


async def run(args: argparse.Namespace) -> int:
    if args.check:
        return await check(args)
    fmt = args.format
    if args.output:
        fmt = "json" if args.output.lower().endswith(".json") else "csv"
    fmt = fmt or "table"

    out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
    writer = None
    gifts: list[Gift] = []
    seen = kept = 0
    try:
        if fmt == "csv":
            writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
        async for gift in collect(args):
            seen += 1
            if not matches(gift, args):
                continue
            kept += 1
            if fmt == "table":
                print_table(gift)
            elif fmt == "csv":
                writer.writerow(gift.to_flat_dict())
                out.flush()
            else:
                gifts.append(gift)
            if args.output and seen % 50 == 0:
                print(f"Обработано: {seen}", file=sys.stderr)
        if fmt == "json":
            gifts.sort(key=lambda g: (g.slug, g.number))
            json.dump([g.to_dict() for g in gifts], out, ensure_ascii=False, indent=2)
            out.write("\n")
    finally:
        if out is not sys.stdout:
            out.close()

    print(f"Готово: загружено {seen}, подошло {kept}" + (f", сохранено в {args.output}" if args.output else ""),
          file=sys.stderr)
    return 0 if seen else 1


def main() -> None:
    ap = build_args()
    args = ap.parse_args()
    if args.list is not None:
        sys.exit(print_collections(args.list))
    if args.owner_lang and (bad := args.owner_lang - OWNER_LANGS.keys()):
        ap.error(f"неизвестный язык владельца: {', '.join(sorted(bad))}. Есть: {', '.join(OWNER_LANGS)}")
    if not args.target:
        ap.error("укажите подарок или коллекцию (или --list)")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        sys.exit(asyncio.run(run(args)))
    except ValueError as exc:
        sys.exit(f"Ошибка: {exc}")
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
