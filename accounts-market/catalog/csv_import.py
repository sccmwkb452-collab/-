"""CSV import of products and stock.

Columns (header row required, `,` or `;` delimiter, UTF-8):

    category,title,price,country,region,short_description,description,specs,items,featured

* category — category title; created (hidden emoji 📦) when missing
* price — rubles, e.g. 1490 or 1490.50
* country — ISO code (DE) or a name (Германия); such products are browsed by country
* specs — characteristics separated by `|`, e.g. `Стаж: 1 год|Почта: в комплекте`
* items — stock units separated by `|` or by line breaks inside a quoted cell
* featured — 1/yes/да to show the product in «Популярное»

A row whose (category, title) already exists updates that product and appends units.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.countries import parse as parse_country
from catalog.manage import add_items, category_by_title, split_items
from database.models import Category, Product
from services.formatting import parse_rubles

REQUIRED = ("category", "title", "price")
MAX_ROWS = 2000


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    items: int = 0
    categories: int = 0
    errors: list[str] = field(default_factory=list)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось прочитать файл: сохраните его в UTF-8")


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "yes", "true", "да", "+"}


async def import_csv(session: AsyncSession, data: bytes) -> ImportReport:
    text = _decode(data)
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError("Файл пуст")
    fields = {f.strip().lower() for f in reader.fieldnames if f}
    missing = [c for c in REQUIRED if c not in fields]
    if missing:
        raise ValueError("Нет обязательных колонок: " + ", ".join(missing))

    report = ImportReport()
    for line_no, raw in enumerate(reader, start=2):
        if line_no - 1 > MAX_ROWS:
            report.errors.append(f"Обработано только {MAX_ROWS} строк")
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        try:
            await _import_row(session, row, report)
        except ValueError as exc:
            report.errors.append(f"Строка {line_no}: {exc}")
    return report


async def _import_row(session: AsyncSession, row: dict[str, str], report: ImportReport) -> None:
    title = row.get("title", "")
    if not title or len(title) > 128:
        raise ValueError("пустое или слишком длинное название")
    price = parse_rubles(row.get("price", ""))
    if price is None:
        raise ValueError("некорректная цена")
    cat_title = row.get("category", "")
    if not cat_title or len(cat_title) > 64:
        raise ValueError("некорректная категория")

    country = None
    if row.get("country"):
        country = parse_country(row["country"])
        if country is None:
            raise ValueError(f"неизвестная страна «{row['country']}»")

    raw_items = row.get("items", "")
    items = split_items(raw_items if "\n" in raw_items else raw_items.replace("|", "\n"))

    async with session.begin_nested():
        category = await category_by_title(session, cat_title)
        if category is None:
            category = Category(title=cat_title, emoji="📦")
            session.add(category)
            await session.flush()
            report.categories += 1

        product = await session.scalar(
            select(Product).where(Product.category_id == category.id, func.lower(Product.title) == title.lower())
        )
        if product is None:
            product = Product(category_id=category.id, title=title, price=price)
            session.add(product)
            report.created += 1
        else:
            product.price = price
            report.updated += 1
        if country:
            product.country = country
        product.region = row.get("region") or product.region
        product.short_description = (row.get("short_description") or product.short_description or "")[:256]
        product.description = row.get("description") or product.description or ""
        if row.get("specs"):
            product.specs = "\n".join(s.strip() for s in row["specs"].split("|") if s.strip())
        if "featured" in row:
            product.is_featured = _truthy(row["featured"])
        await session.flush()
        if items:
            report.items += await add_items(session, product.id, items)
