"""Banner and product-card renderer.

Every screen gets a 1280x640 banner: graphite background, blue / violet / cyan
glow, a thin grid, the shop name and a glyph drawn from vector primitives.
Banners are rendered on demand, so a renamed shop gets new banners at once.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1280, 640
SS = 2  # supersampling for smooth glyph edges

BG_TOP = (11, 13, 18)
BG_BOTTOM = (20, 23, 31)
BLUE = (59, 108, 255)
VIOLET = (139, 92, 246)
CYAN = (34, 211, 238)
PINK = (217, 70, 239)
GREEN = (52, 211, 153)
RED = (248, 113, 113)
AMBER = (251, 191, 36)
WHITE = (240, 244, 255)
MUTED = (148, 160, 190)


@dataclass(frozen=True)
class BannerSpec:
    title: str
    subtitle: str
    glyph: str
    accent: tuple[int, int, int]
    accent2: tuple[int, int, int]


BANNERS: dict[str, BannerSpec] = {
    "home": BannerSpec("Магазин цифровых товаров", "Каталог · Быстрые заказы · Безопасные платежи", "bolt", BLUE, VIOLET),
    "catalog": BannerSpec("Каталог", "Выберите категорию товаров", "grid", BLUE, CYAN),
    "popular": BannerSpec("Популярное", "Самые востребованные позиции", "star", VIOLET, PINK),
    "profile": BannerSpec("Личный кабинет", "Баланс, покупки и операции", "user", CYAN, BLUE),
    "topup": BannerSpec("Пополнение баланса", "Мгновенное зачисление после оплаты", "gem", CYAN, VIOLET),
    "payment": BannerSpec("Счёт на оплату", "Оплата проверяется на стороне провайдера", "card", BLUE, CYAN),
    "orders": BannerSpec("Мои покупки", "История заказов и выданные товары", "box", VIOLET, BLUE),
    "referral": BannerSpec("Реферальная программа", "Приглашайте друзей и получайте бонусы", "gift", PINK, VIOLET),
    "support": BannerSpec("Поддержка", "Поможем с заказом и оплатой", "ring", CYAN, GREEN),
    "rules": BannerSpec("Правила магазина", "Условия покупки и гарантии", "doc", BLUE, VIOLET),
    "checkout": BannerSpec("Оформление заказа", "Проверьте детали перед оплатой", "cart", BLUE, VIOLET),
    "success": BannerSpec("Заказ оформлен", "Товар выдан, спасибо за покупку", "check", GREEN, CYAN),
    "paid": BannerSpec("Оплата получена", "Баланс пополнен", "check", GREEN, CYAN),
    "warning": BannerSpec("Недостаточно средств", "Пополните баланс, чтобы продолжить", "alert", AMBER, PINK),
    "error": BannerSpec("Что-то пошло не так", "Попробуйте ещё раз", "cross", RED, VIOLET),
    "admin": BannerSpec("Админ-панель", "Управление магазином", "shield", VIOLET, BLUE),
}


@lru_cache(maxsize=32)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    names = {
        "xbold": "InterDisplay-ExtraBold.otf",
        "bold": "InterDisplay-Bold.otf",
        "semi": "InterDisplay-SemiBold.otf",
        "regular": "InterDisplay-Regular.otf",
    }
    try:
        return ImageFont.truetype(str(FONTS / names[weight]), size)
    except OSError:  # fonts missing: still render something readable
        return ImageFont.load_default(size)


def _background(accent, accent2, seed: int) -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    grad = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), BG_BOTTOM), img, grad)

    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    shift = (seed % 7) * 22
    for (cx, cy, r, color, k) in (
        (980 + shift, 140, 330, accent, 0.7),
        (760 - shift, 600, 300, accent2, 0.7),
        (120, -40, 260, accent2, 0.35),
    ):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=tuple(int(c * k) for c in color))
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    img = _screen(img, glow)

    grid = Image.new("L", (W, H), 0)
    g = ImageDraw.Draw(grid)
    for x in range(0, W, 48):
        g.line((x, 0, x, H), fill=16)
    for y in range(0, H, 48):
        g.line((0, y, W, y), fill=16)
    fade = Image.linear_gradient("L").rotate(90, expand=True).resize((W, H))
    grid = Image.composite(grid, Image.new("L", (W, H), 0), fade)
    img.paste((150, 170, 255), mask=grid)
    return img


def _screen(base: Image.Image, top: Image.Image) -> Image.Image:
    from PIL import ImageChops

    return ImageChops.screen(base, top)


def _gradient_fill(size: tuple[int, int], c1, c2) -> Image.Image:
    w, h = size
    vertical = Image.linear_gradient("L").resize((w, h))
    mask = Image.blend(vertical, vertical.transpose(Image.Transpose.ROTATE_90), 0.5)
    return Image.composite(Image.new("RGB", size, c2), Image.new("RGB", size, c1), mask)


def _glass_panel(img: Image.Image, box, accent, accent2) -> None:
    x0, y0, x1, y1 = box
    glow = Image.new("RGB", img.size, (0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle((x0 - 10, y0 - 10, x1 + 10, y1 + 10), 70, fill=tuple(c // 2 for c in accent))
    img.paste(_screen(img, glow.filter(ImageFilter.GaussianBlur(40))))

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, 56, fill=(255, 255, 255, 14), outline=(255, 255, 255, 46), width=2)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def _glyph_mask(kind: str, size: int) -> Image.Image:
    """White-on-black mask of a glyph, drawn at SS x resolution."""
    s = size * SS
    m = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(m)
    u = s / 100  # glyph coordinates are in a 100x100 box
    P = lambda pts: [(x * u, y * u) for x, y in pts]  # noqa: E731
    lw = int(7 * u)

    if kind == "bolt":
        d.polygon(P([(58, 4), (18, 58), (46, 58), (38, 96), (82, 38), (54, 38)]), fill=255)
    elif kind == "grid":
        for gx, gy in ((10, 10), (54, 10), (10, 54), (54, 54)):
            d.rounded_rectangle(P([(gx, gy), (gx + 36, gy + 36)]), int(9 * u), fill=255)
    elif kind == "star":
        pts = []
        for i in range(10):
            r = 46 if i % 2 == 0 else 20
            a = -math.pi / 2 + i * math.pi / 5
            pts.append((50 + r * math.cos(a), 52 + r * math.sin(a)))
        d.polygon(P(pts), fill=255)
    elif kind == "user":
        d.ellipse(P([(30, 8), (70, 48)]), fill=255)
        d.chord(P([(10, 56), (90, 136)]), 180, 360, fill=255)
    elif kind == "gem":
        d.polygon(P([(22, 14), (78, 14), (96, 38), (50, 92), (4, 38)]), fill=255)
        d.line(P([(4, 38), (96, 38)]), fill=0, width=int(4 * u))
        d.line(P([(36, 14), (50, 38), (64, 14)]), fill=0, width=int(4 * u))
        d.line(P([(50, 38), (50, 88)]), fill=0, width=int(3 * u))
    elif kind == "card":
        d.rounded_rectangle(P([(4, 18), (96, 82)]), int(10 * u), fill=255)
        d.rectangle(P([(4, 32), (96, 44)]), fill=0)
        d.rounded_rectangle(P([(14, 58), (44, 68)]), int(4 * u), fill=0)
    elif kind == "box":
        d.polygon(P([(50, 6), (92, 26), (50, 46), (8, 26)]), fill=255)
        d.polygon(P([(8, 32), (47, 52), (47, 96), (8, 76)]), fill=200)
        d.polygon(P([(53, 52), (92, 32), (92, 76), (53, 96)]), fill=150)
    elif kind == "gift":
        d.rounded_rectangle(P([(10, 40), (90, 94)]), int(8 * u), fill=255)
        d.rounded_rectangle(P([(4, 26), (96, 44)]), int(6 * u), fill=255)
        d.rectangle(P([(44, 26), (56, 94)]), fill=0)
        d.ellipse(P([(22, 4), (50, 28)]), outline=255, width=lw)
        d.ellipse(P([(50, 4), (78, 28)]), outline=255, width=lw)
    elif kind == "ring":
        d.ellipse(P([(6, 6), (94, 94)]), fill=255)
        d.ellipse(P([(30, 30), (70, 70)]), fill=0)
        for a in (45, 135, 225, 315):
            r = math.radians(a)
            cx, cy = 50 + 32 * math.cos(r), 50 + 32 * math.sin(r)
            d.ellipse(P([(cx - 9, cy - 9), (cx + 9, cy + 9)]), fill=0)
    elif kind == "doc":
        d.rounded_rectangle(P([(16, 4), (84, 96)]), int(10 * u), fill=255)
        for y in (26, 42, 58, 74):
            d.rounded_rectangle(P([(28, y), (72 if y != 74 else 54, y + 6)]), int(3 * u), fill=0)
    elif kind == "cart":
        d.line(P([(4, 14), (20, 14), (30, 66), (82, 66), (92, 28), (24, 28)]), fill=255, width=lw, joint="curve")
        d.polygon(P([(24, 28), (92, 28), (82, 66), (30, 66)]), fill=255)
        d.ellipse(P([(28, 74), (44, 90)]), fill=255)
        d.ellipse(P([(68, 74), (84, 90)]), fill=255)
    elif kind == "check":
        d.ellipse(P([(4, 4), (96, 96)]), fill=255)
        d.line(P([(28, 52), (44, 68), (74, 36)]), fill=0, width=int(10 * u), joint="curve")
    elif kind == "cross":
        d.ellipse(P([(4, 4), (96, 96)]), fill=255)
        d.line(P([(32, 32), (68, 68)]), fill=0, width=int(10 * u))
        d.line(P([(68, 32), (32, 68)]), fill=0, width=int(10 * u))
    elif kind == "alert":
        d.polygon(P([(50, 6), (96, 90), (4, 90)]), fill=255)
        d.rounded_rectangle(P([(45, 34), (55, 64)]), int(4 * u), fill=0)
        d.ellipse(P([(44, 70), (56, 82)]), fill=0)
    elif kind == "shield":
        d.polygon(P([(50, 4), (90, 18), (86, 58), (50, 96), (14, 58), (10, 18)]), fill=255)
        d.line(P([(32, 50), (46, 64), (70, 38)]), fill=0, width=int(8 * u), joint="curve")
    return m.resize((size, size), Image.LANCZOS)


def _draw_glyph(img: Image.Image, kind: str, center: tuple[int, int], size: int, accent, accent2) -> None:
    mask = _glyph_mask(kind, size)
    x, y = center[0] - size // 2, center[1] - size // 2
    halo = Image.new("RGB", img.size, (0, 0, 0))
    halo.paste(accent, (x, y), mask)
    img.paste(_screen(img, halo.filter(ImageFilter.GaussianBlur(18))))
    fill = _gradient_fill((size, size), tuple(min(255, c + 70) for c in accent), accent2)
    img.paste(Image.blend(fill, Image.new("RGB", fill.size, WHITE), 0.5), (x, y), mask)


def _pill(d: ImageDraw.ImageDraw, xy, text: str, f, fg, bg, outline=None, pad=(18, 9)) -> int:
    x, y = xy
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    w, h = r - l + pad[0] * 2, b - t + pad[1] * 2
    d.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=bg, outline=outline, width=2)
    d.text((x + pad[0] - l, y + pad[1] - t), text, font=f, fill=fg)
    return x + w


def _fit(d: ImageDraw.ImageDraw, text: str, weight: str, start: int, max_width: int, min_size: int = 30):
    size = start
    while size > min_size and d.textlength(text, font=font(weight, size)) > max_width:
        size -= 2
    return font(weight, size)


def _wrap(d: ImageDraw.ImageDraw, text: str, f, max_width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=f) <= max_width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        while lines[-1] and d.textlength(lines[-1] + "…", font=f) > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def _brand(d: ImageDraw.ImageDraw, shop_name: str, accent) -> None:
    d.ellipse((72, 66, 90, 84), fill=accent)
    d.text((104, 60), shop_name.upper(), font=font("bold", 26), fill=WHITE)


def _encode(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True, progressive=True)
    return buf.getvalue()


def render_banner(key: str, shop_name: str) -> bytes:
    spec = BANNERS.get(key, BANNERS["home"])
    img = _background(spec.accent, spec.accent2, seed=sum(map(ord, key)))
    _glass_panel(img, (850, 130, 1210, 490), spec.accent, spec.accent2)
    _draw_glyph(img, spec.glyph, (1030, 310), 200, spec.accent, spec.accent2)

    d = ImageDraw.Draw(img)
    _brand(d, shop_name, spec.accent)
    if key == "home":
        title_font = _fit(d, shop_name.upper(), "xbold", 92, 720)
        d.text((72, 214), shop_name.upper(), font=title_font, fill=WHITE)
        d.text((76, 340), spec.title, font=font("semi", 38), fill=(200, 210, 240))
    else:
        title_font = _fit(d, spec.title, "xbold", 80, 720)
        d.text((72, 230), spec.title, font=title_font, fill=WHITE)
    d.text((76, 410), spec.subtitle, font=font("regular", 28), fill=MUTED)
    d.rounded_rectangle((76, 480, 196, 486), 3, fill=spec.accent)
    d.rounded_rectangle((204, 480, 244, 486), 3, fill=spec.accent2)
    return _encode(img)


def render_product_card(
    *,
    shop_name: str,
    title: str,
    category: str,
    region: str | None,
    price: str,
    stock: int,
    demo: bool,
) -> bytes:
    accent, accent2 = (VIOLET, BLUE) if stock > 0 else (MUTED, VIOLET)
    img = _background(accent, accent2, seed=len(title))
    _glass_panel(img, (900, 150, 1210, 460), accent, accent2)
    _draw_glyph(img, "gem", (1055, 305), 170, CYAN if stock > 0 else MUTED, accent)

    d = ImageDraw.Draw(img)
    _brand(d, shop_name, accent)
    x = 72
    x = _pill(d, (x, 130), category.upper(), font("semi", 22), WHITE, (36, 40, 58), outline=(70, 78, 110)) + 12
    if region:
        x = _pill(d, (x, 130), region, font("semi", 22), WHITE, (30, 45, 70), outline=(60, 100, 160)) + 12
    if demo:
        _pill(d, (x, 130), "DEMO", font("bold", 22), (20, 20, 20), AMBER)

    for size, max_lines in ((62, 2), (52, 2), (46, 3)):
        title_font = font("xbold", size)
        lines = _wrap(d, title, title_font, 790, max_lines)
        if not lines[-1].endswith("…"):
            break
    y = 205 if len(lines) < 3 else 195
    for line in lines:
        d.text((72, y), line, font=title_font, fill=WHITE)
        y += int(title_font.size * 1.15)

    d.text((72, 440), price, font=font("xbold", 72), fill=WHITE)
    if stock > 0:
        status, color, bg = f"В наличии · {stock} шт.", GREEN, (20, 50, 44)
    else:
        status, color, bg = "Нет в наличии", RED, (60, 28, 32)
    _pill(d, (76, 545), status, font("semi", 24), color, bg, outline=tuple(c // 2 for c in color))
    return _encode(img)


if __name__ == "__main__":  # python -m bot.banners  → previews into assets/banners
    out = FONTS.parent / "banners"
    out.mkdir(exist_ok=True)
    for name in BANNERS:
        (out / f"{name}.jpg").write_bytes(render_banner(name, "ACCOUNTS MARKET"))
    (out / "product_card.jpg").write_bytes(
        render_product_card(
            shop_name="ACCOUNTS MARKET",
            title="DEMO · Premium-аккаунт сервиса на 12 месяцев",
            category="Новые товары",
            region="EU",
            price="1 490 ₽",
            stock=12,
            demo=True,
        )
    )
    print(f"saved to {out}")
