"""Image templates registry and listing image generation.

* ``assets/templates/demo/`` — demonstration templates created by the
  system (a base PNG + layout). They contain no brand logos.
* ``assets/templates/originals/`` — the owner's templates. Files there are
  never modified. A template becomes usable when a layout ``<name>.json``
  sits next to the image; without it the template is registered as
  inactive with its size, format and palette for the layout to be made.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.models import ImageTemplate, ListingImage, Product
from ..shared.errors import DomainError, NotFound
from ..shared.money import fmt_money
from . import generator

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")

# Layouts of the demonstration templates (coordinates for the base size).
DEMO_LAYOUTS: dict[str, dict[str, Any]] = {
    "demo-graphite": {
        "name": "Графит — универсальный",
        "size": [1200, 800],
        "palette": {"from": "#0B1020", "to": "#111C3A", "glow": "#2563EB", "accent": "#38BDF8"},
        "groups": [],
        "fields": [
            {"name": "category", "box": [72, 64, 700, 56], "font": "Inter-SemiBold.otf", "size": 26, "min_size": 18, "color": "#BFDBFE",
             "max_lines": 1, "uppercase": True, "badge": {"fill": "#1E3A8A", "radius": 14, "pad_x": 18, "pad_y": 9}},
            {"name": "title", "box": [72, 170, 1056, 230], "font": "Inter-ExtraBold.otf", "size": 78, "min_size": 40, "color": "#FFFFFF",
             "max_lines": 3, "required": True},
            {"name": "nominal", "box": [72, 430, 760, 130], "font": "Inter-ExtraBold.otf", "size": 104, "min_size": 56, "color": "#38BDF8",
             "max_lines": 1},
            {"name": "region", "box": [72, 600, 520, 60], "font": "Inter-SemiBold.otf", "size": 28, "min_size": 18, "color": "#E2E8F0",
             "max_lines": 1, "badge": {"fill": "#1F2937", "radius": 14, "pad_x": 18, "pad_y": 10}},
            {"name": "subtitle", "box": [72, 690, 760, 50], "font": "Inter-Medium.otf", "size": 30, "min_size": 20, "color": "#94A3B8",
             "max_lines": 1},
            {"name": "price", "box": [760, 660, 368, 90], "font": "Inter-ExtraBold.otf", "size": 60, "min_size": 34, "color": "#FFFFFF",
             "align": "right", "valign": "bottom", "max_lines": 1, "badge": {"fill": "#16A34A", "radius": 18, "pad_x": 24, "pad_y": 12}},
        ],
    },
    "demo-telegram": {
        "name": "Telegram — Stars и Premium",
        "size": [1200, 800],
        "palette": {"from": "#0A1633", "to": "#1D4ED8", "glow": "#60A5FA", "accent": "#FACC15"},
        "groups": ["telegram"],
        "fields": [
            {"name": "category", "box": [72, 64, 700, 56], "font": "Inter-SemiBold.otf", "size": 26, "min_size": 18, "color": "#0A1633",
             "max_lines": 1, "uppercase": True, "badge": {"fill": "#FACC15", "radius": 14, "pad_x": 18, "pad_y": 9}},
            {"name": "nominal", "box": [72, 170, 1056, 200], "font": "Inter-ExtraBold.otf", "size": 150, "min_size": 70, "color": "#FFFFFF",
             "max_lines": 1},
            {"name": "title", "box": [72, 400, 1056, 150], "font": "Inter-Bold.otf", "size": 54, "min_size": 30, "color": "#DBEAFE",
             "max_lines": 2, "required": True},
            {"name": "subtitle", "box": [72, 600, 700, 60], "font": "Inter-Medium.otf", "size": 32, "min_size": 20, "color": "#BFDBFE",
             "max_lines": 1},
            {"name": "region", "box": [72, 680, 500, 60], "font": "Inter-SemiBold.otf", "size": 28, "min_size": 18, "color": "#FFFFFF",
             "max_lines": 1, "badge": {"fill": "#1E40AF", "radius": 14, "pad_x": 18, "pad_y": 10}},
            {"name": "price", "box": [760, 660, 368, 90], "font": "Inter-ExtraBold.otf", "size": 60, "min_size": 34, "color": "#0A1633",
             "align": "right", "valign": "bottom", "max_lines": 1, "badge": {"fill": "#FFFFFF", "radius": 18, "pad_x": 24, "pad_y": 12}},
        ],
    },
    "demo-square": {
        "name": "Квадрат — карточка кода",
        "size": [1080, 1080],
        "palette": {"from": "#0B1020", "to": "#0F2A4A", "glow": "#0EA5E9", "accent": "#22C55E"},
        "groups": ["giftcards", "steam", "games", "roblox", "subscriptions"],
        "fields": [
            {"name": "category", "box": [80, 80, 920, 56], "font": "Inter-SemiBold.otf", "size": 28, "min_size": 18, "color": "#A5F3FC",
             "max_lines": 1, "uppercase": True, "align": "center", "badge": {"fill": "#164E63", "radius": 14, "pad_x": 20, "pad_y": 9}},
            {"name": "nominal", "box": [80, 300, 920, 220], "font": "Inter-ExtraBold.otf", "size": 170, "min_size": 70, "color": "#FFFFFF",
             "max_lines": 1, "align": "center", "valign": "middle"},
            {"name": "title", "box": [80, 560, 920, 180], "font": "Inter-Bold.otf", "size": 58, "min_size": 30, "color": "#E0F2FE",
             "max_lines": 2, "align": "center", "required": True},
            {"name": "region", "box": [80, 780, 920, 64], "font": "Inter-SemiBold.otf", "size": 30, "min_size": 18, "color": "#FFFFFF",
             "max_lines": 1, "align": "center", "badge": {"fill": "#1F2937", "radius": 16, "pad_x": 20, "pad_y": 10}},
            {"name": "subtitle", "box": [80, 880, 920, 50], "font": "Inter-Medium.otf", "size": 30, "min_size": 20, "color": "#94A3B8",
             "max_lines": 1, "align": "center"},
            {"name": "price", "box": [80, 950, 920, 90], "font": "Inter-ExtraBold.otf", "size": 56, "min_size": 32, "color": "#FFFFFF",
             "max_lines": 1, "align": "center", "valign": "bottom", "badge": {"fill": "#16A34A", "radius": 18, "pad_x": 26, "pad_y": 10}},
        ],
    },
}  # fmt: skip


def templates_dir() -> Path:
    return get_settings().assets_dir / "templates"


def _rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def build_demo_base(code: str) -> Image.Image:
    """Abstract background: diagonal gradient, soft glow, faint grid. No logos."""
    spec = DEMO_LAYOUTS[code]
    w, h = spec["size"]
    pal = spec["palette"]
    a, b = _rgb(pal["from"]), _rgb(pal["to"])
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(0, w, 2):
            t = min(1.0, (x / w) * 0.55 + (y / h) * 0.45)
            col = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
            px[x, y] = col
            if x + 1 < w:
                px[x + 1, y] = col
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gr = _rgb(pal["glow"])
    radius = int(min(w, h) * 0.55)
    cx, cy = int(w * 0.86), int(h * 0.18)
    gd.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*gr, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(radius // 2))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    step = 48
    for gx in range(0, w, step):
        od.line((gx, 0, gx, h), fill=(255, 255, 255, 9))
    for gy in range(0, h, step):
        od.line((0, gy, w, gy), fill=(255, 255, 255, 9))
    ac = _rgb(pal["accent"])
    for i in range(5):
        r = 4 + i * 2
        ang = i * 1.25
        x = int(w * 0.90 + math.cos(ang) * w * 0.05)
        y = int(h * 0.11 + math.sin(ang) * h * 0.06)
        od.ellipse((x - r, y - r, x + r, y + r), fill=(*ac, 120))
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def ensure_demo_files() -> list[Path]:
    out = []
    demo = templates_dir() / "demo"
    demo.mkdir(parents=True, exist_ok=True)
    for code, spec in DEMO_LAYOUTS.items():
        path = demo / f"{code}.png"
        if not path.exists():
            build_demo_base(code).save(path, optimize=True)
        layout = demo / f"{code}.json"
        payload = {"name": spec["name"], "groups": spec["groups"], "fields": spec["fields"]}
        if not layout.exists() or json.loads(layout.read_text(encoding="utf-8")) != payload:
            layout.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        out.append(path)
    return out


async def sync_registry(session: AsyncSession) -> dict[str, int]:
    """Register demo templates and the owner's originals. A layout without its
    image is registered as «ждёт файл», an image without a layout as «нужна разметка»."""
    ensure_demo_files()
    stats = {"demo": 0, "user": 0, "needs_layout": 0, "awaiting_file": 0}
    existing = {t.code: t for t in (await session.execute(select(ImageTemplate))).scalars()}
    for kind in ("demo", "originals"):
        folder = templates_dir() / kind
        folder.mkdir(parents=True, exist_ok=True)
        stems = sorted({p.stem for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT or p.suffix.lower() == ".json"})
        for stem in stems:
            image = next((folder / f"{stem}{ext}" for ext in IMAGE_EXT if (folder / f"{stem}{ext}").exists()), None)
            layout_path = folder / f"{stem}.json"
            layout = json.loads(layout_path.read_text(encoding="utf-8")) if layout_path.exists() else None
            code = stem if kind == "demo" else f"user-{stem}"[:64]
            info = generator.analyze(image) if image else {"width": 0, "height": 0, "format": None, "palette": []}
            spec = dict(layout or {})
            spec["analysis"] = info
            spec.setdefault("fields", [])
            row = existing.get(code)
            if row is None:
                row = ImageTemplate(code=code, kind="demo" if kind == "demo" else "user", base_path="", width=0, height=0)
                session.add(row)
            row.base_path = f"{kind}/{image.name}" if image else f"{kind}/{stem}.png"
            row.name = (layout or {}).get("name") or stem
            row.category_groups = (layout or {}).get("groups", [])
            row.spec = spec
            row.width, row.height = info["width"], info["height"]
            row.active = bool(image and layout and layout.get("fields"))
            if kind == "demo":
                stats["demo"] += 1
            else:
                stats["user"] += 1
                if image is None:
                    stats["awaiting_file"] += 1
                elif not row.active:
                    stats["needs_layout"] += 1
    await session.flush()
    return stats


def template_state(t: ImageTemplate) -> str:
    if t.active:
        return "active"
    return "awaiting_file" if not t.width else "needs_layout"


async def list_templates(session: AsyncSession) -> list[ImageTemplate]:
    return list((await session.execute(select(ImageTemplate).order_by(ImageTemplate.kind.desc(), ImageTemplate.code))).scalars())


async def pick_template(session: AsyncSession, product: Product, code: str | None = None) -> ImageTemplate:
    code = code or product.image_template
    if code:
        tpl = (await session.execute(select(ImageTemplate).where(ImageTemplate.code == code))).scalar_one_or_none()
        if tpl is None:
            raise NotFound("Шаблон не найден")
        if not tpl.active:
            state = template_state(tpl)
            raise DomainError(
                "Шаблон ждёт файл изображения" if state == "awaiting_file" else "Шаблон без разметки полей — его нельзя использовать"
            )
        return tpl
    templates = [t for t in await list_templates(session) if t.active]
    category = product.category
    for t in templates:  # the owner's template made for this category
        if t.kind == "user" and category.code in (t.spec.get("categories") or []):
            return t
    for preferred in ([t for t in templates if t.kind == "user"], templates):
        for t in preferred:
            if category.image_template == t.code or category.group in (t.category_groups or []):
                return t
    fallback = next((t for t in templates if t.code == "demo-graphite"), None) or (templates[0] if templates else None)
    if fallback is None:
        raise DomainError("Нет активных шаблонов изображений")
    return fallback


def plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]


AMOUNT_WORDS = {
    "STARS": ("звезда", "звезды", "звёзд"),
    "MONTHS": ("месяц", "месяца", "месяцев"),
}
CURRENCY_SIGNS = {"USD": "$", "EUR": "€", "RUB": "₽", "GBP": "£"}


def amount_of(product: Product) -> int | None:
    if product.face_value is not None and (product.face_currency or "").upper() not in CURRENCY_SIGNS:
        return int(product.face_value)
    if (product.supplier_quantity or 1) > 1:
        return int(product.supplier_quantity)
    digits = re.search(r"\d[\d\s\u202f\u00a0]*", product.name)
    if digits:
        number = re.sub(r"\D", "", digits.group(0))
        return int(number) if number else None
    return None


def values_for(product: Product, price: Any | None = None, overrides: dict[str, str] | None = None) -> dict[str, str]:
    nominal = ""
    face_short = ""
    currency = (product.face_currency or "").upper()
    if product.face_value is not None:
        face = f"{product.face_value.normalize():f}"
        nominal = f"{face} {product.face_currency or ''}".strip()
        face_short = f"{face}{CURRENCY_SIGNS[currency]}" if currency in CURRENCY_SIGNS else nominal
    amount = amount_of(product)
    word = ""
    if amount is not None:
        kind = currency if currency in AMOUNT_WORDS else {"tg_stars": "STARS", "tg_premium": "MONTHS"}.get(product.category.code, "")
        if kind:
            word = plural_ru(amount, AMOUNT_WORDS[kind])
    values = {
        "amount": "" if amount is None else str(amount),
        "amount_word": word,
        "face_short": face_short,
        "title": product.name,
        "category": product.category.name,
        "nominal": nominal,
        "region": f"Регион: {product.region}" if product.region else "",
        "subtitle": f"Выдача: {product.delivery_time}" if product.delivery_time else "",
        "price": fmt_money(price) if price else "",
    }
    values.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return values


async def generate_for_product(
    session: AsyncSession,
    product: Product,
    *,
    template_code: str | None = None,
    listing_id: int | None = None,
    listing_version: int | None = None,
    price: Any | None = None,
    overrides: dict[str, str] | None = None,
    preview: bool = False,
) -> ListingImage:
    tpl = await pick_template(session, product, template_code)
    base = templates_dir() / tpl.base_path
    result = generator.render(base, tpl.spec, values_for(product, price, overrides))
    folder = get_settings().storage_dir / "images" / str(product.id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{'preview' if preview else f'v{listing_version or 0}'}-{tpl.code}-{result.sha256[:12]}.png"
    (folder / name).write_bytes(result.data)
    image = ListingImage(
        listing_id=listing_id,
        product_id=product.id,
        listing_version=listing_version,
        template_code=tpl.code,
        path=f"images/{product.id}/{name}",
        width=result.width,
        height=result.height,
        sha256=result.sha256,
        is_preview=preview,
    )
    session.add(image)
    await session.flush()
    return image


def image_path(image: ListingImage) -> Path:
    path = (get_settings().storage_dir / image.path).resolve()
    root = get_settings().storage_dir.resolve()
    if root not in path.parents:
        raise NotFound("Файл вне хранилища")
    return path
