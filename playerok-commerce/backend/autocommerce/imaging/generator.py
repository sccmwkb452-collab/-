"""Listing image generator (Pillow).

A template is a base image (never modified: it is opened read-only and copied
in memory) plus a JSON layout. Coordinates are pixels, or fractions of the
image size when the layout says ``"units": "relative"`` — then font sizes are
fractions of the image height and the layout works for any export size.

Layout keys:

* ``erase`` — areas of the original to clean before drawing:
  ``mode: "text"`` removes light text (bright, unsaturated pixels) and fills
  the hole from the surrounding background (normalised Gaussian fill);
  ``mode: "fill"`` refills the whole rectangle the same way;
  ``mode: "pill"`` redraws a rounded plate with a vertical gradient sampled
  from two points of the original.
* ``fields`` — text fields:
  ``{"name", "box", "font", "size", "min_size", "color", "align", "valign",
  "max_lines", "template", "required", "badge", "extrude", "shadow"}``.
  ``template`` builds the text from values (``"{amount} {amount_word}"``).
  Fonts: a file from assets/fonts, a variable font instance as
  ``"Unbounded-VF.ttf:Bold"``.

Text is wrapped by words and shrunk down to ``min_size``; if it still does not
fit, the last line ends with an ellipsis. Optional fields without a value are
skipped. Characters the font cannot draw (emoji) are dropped instead of
printing «no glyph» boxes.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from ..config import get_settings

ELLIPSIS = "…"
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]{0,40})\}")


class TemplateError(ValueError):
    pass


@dataclass
class TextField:
    name: str
    box: tuple[int, int, int, int]
    font: str = "Inter-Bold.otf"
    size: int = 48
    min_size: int = 20
    color: str = "#FFFFFF"
    align: str = "left"
    valign: str = "top"
    max_lines: int = 2
    line_spacing: float = 1.12
    uppercase: bool = False
    required: bool = False
    template: str | None = None
    badge: dict[str, Any] | None = None
    extrude: dict[str, Any] | None = None
    shadow: dict[str, Any] | None = None

    @classmethod
    def from_spec(cls, spec: dict[str, Any], scale: tuple[float, float] | None = None) -> TextField:
        """``scale`` = (width, height) for relative layouts."""
        box = list(spec["box"])
        size = spec.get("size", 48)
        min_size = spec.get("min_size")
        if scale:
            w, h = scale
            box = [box[0] * w, box[1] * h, box[2] * w, box[3] * h]
            size = size * h
            min_size = None if min_size is None else min_size * h
        size = int(round(size))
        badge = _scale_dict(spec.get("badge"), scale, ("pad_x", "pad_y", "radius"))
        extrude = _scale_dict(spec.get("extrude"), scale, ("depth",))
        shadow = _scale_dict(spec.get("shadow"), scale, ("dx", "dy", "blur"))
        return cls(
            name=spec["name"],
            box=(int(round(box[0])), int(round(box[1])), int(round(box[2])), int(round(box[3]))),
            font=spec.get("font", "Inter-Bold.otf"),
            size=size,
            min_size=int(round(min_size)) if min_size is not None else max(12, size // 2),
            color=spec.get("color", "#FFFFFF"),
            align=spec.get("align", "left"),
            valign=spec.get("valign", "top"),
            max_lines=int(spec.get("max_lines", 2)),
            line_spacing=float(spec.get("line_spacing", 1.12)),
            uppercase=bool(spec.get("uppercase", False)),
            required=bool(spec.get("required", False)),
            template=spec.get("template"),
            badge=badge,
            extrude=extrude,
            shadow=shadow,
        )


def _scale_dict(data: dict[str, Any] | None, scale: tuple[float, float] | None, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if data is None or scale is None:
        return data
    out = dict(data)
    h = scale[1]
    for key in keys:
        if key in out and isinstance(out[key], (int, float)) and abs(out[key]) < 1:
            out[key] = out[key] * h
    return out


@dataclass
class Layout:
    lines: list[str]
    font_size: int
    truncated: bool
    line_height: int
    width: int
    height: int


@dataclass
class RenderResult:
    data: bytes
    width: int
    height: int
    sha256: str
    layouts: dict[str, Layout] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


def fonts_dir() -> Path:
    return get_settings().assets_dir / "fonts"


@lru_cache(maxsize=256)
def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """``Inter-Bold.otf`` or a variable font instance ``Unbounded-VF.ttf:Bold``."""
    file_name, _, variation = name.partition(":")
    path = fonts_dir() / Path(file_name).name  # no path traversal through the layout
    if not path.exists():
        path = fonts_dir() / "Inter-Regular.otf"
        variation = ""
    font = ImageFont.truetype(str(path), size)
    if variation:
        try:
            font.set_variation_by_name(variation)
        except (OSError, ValueError) as exc:
            raise TemplateError(f"У шрифта {file_name} нет начертания {variation}") from exc
    return font


@lru_cache(maxsize=64)
def _notdef(name: str) -> bytes:
    return bytes(load_font(name, 40).getmask("\U0010fffd"))


@lru_cache(maxsize=8192)
def _has_glyph(name: str, ch: str) -> bool:
    if ch.isspace():
        return True
    return bytes(load_font(name, 40).getmask(ch)) != _notdef(name)


def supported_text(text: str, font_name: str) -> str:
    """Drop characters the font cannot draw (emoji etc.)."""
    kept = "".join(ch for ch in text if _has_glyph(font_name, ch))
    return re.sub(r"[ \t]{2,}", " ", kept).strip()


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.getlength(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    out: list[str] = []
    for line in lines:  # a single word wider than the box is split by characters
        while font.getlength(line) > width and len(line) > 1:
            cut = len(line)
            while cut > 1 and font.getlength(line[:cut]) > width:
                cut -= 1
            out.append(line[:cut])
            line = line[cut:]
        out.append(line)
    return out


def _ellipsize(line: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    if font.getlength(line + ELLIPSIS) <= width:
        return line + ELLIPSIS
    while line and font.getlength(line.rstrip() + ELLIPSIS) > width:
        line = line[:-1]
    return line.rstrip() + ELLIPSIS


def fit_text(text: str, f: TextField) -> Layout:
    _, _, width, height = f.box
    if f.badge:
        width -= 2 * int(f.badge.get("pad_x", 16))
        height -= 2 * int(f.badge.get("pad_y", 8))
    text = supported_text(text.upper() if f.uppercase else text, f.font)
    size = f.size
    step = max(1, f.size // 40)
    while True:
        font = load_font(f.font, size)
        line_height = int(round(size * f.line_spacing))
        lines = _wrap(text, font, width)
        if not lines:
            return Layout([], size, False, line_height, 0, 0)
        if len(lines) <= f.max_lines and line_height * len(lines) <= height + int(size * 0.25):
            return Layout(lines, size, False, line_height, int(max(font.getlength(x) for x in lines)), line_height * len(lines))
        if size <= f.min_size:
            kept = lines[: max(1, min(f.max_lines, max(1, height // max(1, line_height))))]
            if len(lines) > len(kept):
                kept[-1] = _ellipsize(kept[-1], font, width)
            return Layout(kept, size, True, line_height, int(max(font.getlength(x) for x in kept)), line_height * len(kept))
        size = max(f.min_size, size - step)


def hex_color(color: str) -> tuple[int, int, int, int]:
    c = color.lstrip("#")
    if len(c) == 6:
        c += "ff"
    if len(c) != 8 or not re.fullmatch(r"[0-9a-fA-F]{8}", c):
        raise TemplateError(f"Цвет {color!r} должен быть в формате #RRGGBB или #RRGGBBAA")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore[return-value]


# --- erasing baked-in text ---------------------------------------------------------


def _box(spec: dict[str, Any], scale: tuple[float, float] | None) -> tuple[int, int, int, int]:
    x, y, w, h = spec["box"]
    if scale:
        x, y, w, h = x * scale[0], y * scale[1], w * scale[0], h * scale[1]
    return int(round(x)), int(round(y)), int(round(w)), int(round(h))


def text_mask(region: Image.Image, min_brightness: int = 200, max_saturation: int = 70, dilate: int = 4) -> Image.Image:
    """Mask (L) of light, unsaturated pixels — white or near-white lettering."""
    hsv = region.convert("RGB").convert("HSV")
    _, sat, val = hsv.split()
    bright = val.point(lambda v: 255 if v >= min_brightness else 0)
    pale = sat.point(lambda s: 255 if s <= max_saturation else 0)
    mask = ImageChops.multiply(bright, pale)
    size = max(3, 2 * int(dilate) + 1)
    return mask.filter(ImageFilter.MaxFilter(size if size % 2 else size + 1))


def fill_from_surroundings(region: Image.Image, mask: Image.Image, radius: float, exclude: Image.Image | None = None) -> Image.Image:
    """Normalised Gaussian fill: masked pixels get the weighted average of the
    known neighbourhood. ``exclude`` marks pixels that must not be used as a
    source either (other lettering nearby), so no light halo bleeds in."""
    base = region.convert("RGBA")
    unknown = mask if exclude is None else ImageChops.lighter(mask, exclude)
    known = base.copy()
    known.putalpha(ImageChops.invert(unknown))
    result = base.copy()
    remaining = mask
    r = max(2.0, radius)
    for _ in range(6):
        blurred = known.convert("RGBa").filter(ImageFilter.GaussianBlur(r)).convert("RGBA")
        alpha = blurred.getchannel("A")
        covered = ImageChops.multiply(remaining, alpha.point(lambda a: 255 if a >= 8 else 0))
        opaque = blurred.copy()
        opaque.putalpha(255)
        result.paste(opaque, (0, 0), covered)
        remaining = ImageChops.subtract(remaining, covered)
        if remaining.getbbox() is None:
            break
        r *= 2
    soft = mask.filter(ImageFilter.GaussianBlur(1.2))
    return Image.composite(result, base, soft).convert(region.mode)


def erase(canvas: Image.Image, spec: dict[str, Any], scale: tuple[float, float] | None) -> None:
    x, y, w, h = _box(spec, scale)
    if w <= 0 or h <= 0:
        return
    mode = spec.get("mode", "text")
    if mode == "pill":
        _redraw_pill(canvas, (x, y, w, h), spec, scale)
        return
    pad = int(max(w, h) * 0.25)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(canvas.width, x + w + pad), min(canvas.height, y + h + pad)
    region = canvas.crop((x0, y0, x1, y1))
    inner = Image.new("L", region.size, 0)
    ImageDraw.Draw(inner).rectangle((x - x0, y - y0, x - x0 + w, y - y0 + h), fill=255)
    lettering = text_mask(
        region, int(spec.get("min_brightness", 200)), int(spec.get("max_saturation", 70)), int(spec.get("dilate", max(3, h // 40)))
    )
    mask = ImageChops.multiply(lettering, inner) if mode == "text" else inner
    radius = float(spec.get("radius", max(6, h // 6)))
    canvas.paste(fill_from_surroundings(region, mask, radius, exclude=lettering), (x0, y0))


def _redraw_pill(canvas: Image.Image, box: tuple[int, int, int, int], spec: dict[str, Any], scale: tuple[float, float] | None) -> None:
    x, y, w, h = box

    def point(p: list[float]) -> tuple[int, int]:
        return (int(p[0] * scale[0]), int(p[1] * scale[1])) if scale else (int(p[0]), int(p[1]))

    top = canvas.getpixel(point(spec["sample_top"]))[:3]
    bottom = canvas.getpixel(point(spec["sample_bottom"]))[:3]
    gradient = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(gradient)
    for row in range(h):
        t = row / max(1, h - 1)
        gd.line((0, row, w, row), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    mask = Image.new("L", (w, h), 0)
    radius = int(h * float(spec.get("radius", 0.5)))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1))
    canvas.paste(gradient.convert(canvas.mode), (x, y), mask)


# --- drawing -----------------------------------------------------------------------


def _draw_lines(canvas: Image.Image, f: TextField, layout: Layout) -> None:
    draw = ImageDraw.Draw(canvas)
    font = load_font(f.font, layout.font_size)
    x, y, w, h = f.box
    if f.badge:
        pad_x, pad_y = int(f.badge.get("pad_x", 16)), int(f.badge.get("pad_y", 8))
        badge_w = min(w, layout.width + 2 * pad_x)
        badge_h = layout.height + 2 * pad_y
        bx = x if f.align == "left" else (x + w - badge_w if f.align == "right" else x + (w - badge_w) // 2)
        by = y if f.valign == "top" else (y + h - badge_h if f.valign == "bottom" else y + (h - badge_h) // 2)
        draw.rounded_rectangle(
            (bx, by, bx + badge_w, by + badge_h), radius=int(f.badge.get("radius", 12)), fill=hex_color(f.badge.get("fill", "#2563EB"))
        )
        x, y, w, h = bx + pad_x, by + pad_y, badge_w - 2 * pad_x, badge_h - 2 * pad_y
    anchor = None
    positions = []
    if f.valign == "baseline" and not f.badge:
        # (x, y + h) is the baseline of the last line
        anchor = {"left": "ls", "right": "rs", "center": "ms"}.get(f.align, "ls")
        n = len(layout.lines)
        for i, line in enumerate(layout.lines):
            lx = x if f.align == "left" else (x + w if f.align == "right" else x + w / 2)
            positions.append((lx, y + h - (n - 1 - i) * layout.line_height, line))
    else:
        top = y if f.valign == "top" or f.badge else (y + h - layout.height if f.valign == "bottom" else y + (h - layout.height) // 2)
        for i, line in enumerate(layout.lines):
            line_w = font.getlength(line)
            lx = x if f.align == "left" else (x + w - line_w if f.align == "right" else x + (w - line_w) / 2)
            positions.append((lx, top + i * layout.line_height, line))
    if f.shadow:
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        dx, dy = float(f.shadow.get("dx", 0)), float(f.shadow.get("dy", 4))
        for lx, ly, line in positions:
            ld.text((lx + dx, ly + dy), line, font=font, fill=hex_color(f.shadow.get("color", "#00000066")), anchor=anchor)
        layer = layer.filter(ImageFilter.GaussianBlur(float(f.shadow.get("blur", 4))))
        canvas.alpha_composite(layer)
    if f.extrude:
        depth = int(f.extrude.get("depth", 8))
        vx, vy = f.extrude.get("direction", [0.35, 1])
        norm = max(1e-6, (vx * vx + vy * vy) ** 0.5)
        color = hex_color(f.extrude.get("color", "#1D4ED8"))
        for step in range(depth, 0, -1):
            for lx, ly, line in positions:
                draw.text((lx + vx / norm * step, ly + vy / norm * step), line, font=font, fill=color, anchor=anchor)
    for lx, ly, line in positions:
        draw.text((lx, ly), line, font=font, fill=hex_color(f.color), anchor=anchor)


def calibrate(
    canvas: Image.Image, field_spec: dict[str, Any], erase_spec: dict[str, Any], scale: tuple[float, float] | None
) -> dict[str, Any] | None:
    """Match a field to the lettering it replaces. Measures the first glyph of
    the original text (light pixels in the erase box): its left edge, height
    and baseline; returns a pixel-based field spec with the font size that
    gives the reference glyph the same height. None when nothing is found."""
    cal = field_spec.get("calibrate") or {}
    x, y, w, h = _box(erase_spec, scale)
    region = canvas.crop((x, y, x + w, y + h))
    mask = text_mask(region, int(erase_spec.get("min_brightness", 200)), int(erase_spec.get("max_saturation", 70)), dilate=0)
    bbox = mask.getbbox()
    if bbox is None:
        return None
    # the first glyph ends at the first empty column after the text starts
    end = bbox[0] + 1
    while end < bbox[2] and mask.crop((end, 0, end + 1, mask.height)).getbbox() is not None:
        end += 1
    head = mask.crop((bbox[0], 0, end, mask.height))
    gb = head.getbbox()
    if gb is None or gb[3] - gb[1] < 6:
        return None
    measured = gb[3] - gb[1]
    glyph = cal.get("glyph", "0")
    ref = load_font(field_spec.get("font", "Inter-Bold.otf"), 200).getbbox(glyph, anchor="ls")
    ref_height = ref[3] - ref[1]
    if ref_height <= 0:
        return None
    size = measured * 200 / ref_height
    left_bearing = ref[0] * size / 200
    baseline = y + gb[3] - ref[3] * size / 200  # glyphs like «з» or «$» reach below the baseline
    out = dict(field_spec)
    box = list(field_spec["box"])
    if scale:
        box = [box[0] * scale[0], box[1] * scale[1], box[2] * scale[0], box[3] * scale[1]]
    left = x + bbox[0] - left_bearing
    out["box"] = [left, baseline - box[3], box[0] + box[2] - left, box[3]]
    out["size"] = size
    ratio = float(field_spec.get("min_size", field_spec.get("size", 1) * 0.5)) / float(field_spec.get("size", 1) or 1)
    out["min_size"] = size * ratio
    out["valign"] = "baseline"
    out["badge"] = _scale_dict(field_spec.get("badge"), scale, ("pad_x", "pad_y", "radius"))
    out["extrude"] = _scale_dict(field_spec.get("extrude"), scale, ("depth",))
    out["shadow"] = _scale_dict(field_spec.get("shadow"), scale, ("dx", "dy", "blur"))
    out.pop("calibrate", None)
    return out


def resolve_value(spec: dict[str, Any], values: dict[str, str | None]) -> str:
    template = spec.get("template")
    if template:
        missing = [m.group(1) for m in _PLACEHOLDER.finditer(template) if not values.get(m.group(1))]
        if missing:
            return ""
        return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1)) or ""), template).strip()
    return (values.get(spec["name"]) or "").strip()


def render(
    base: Path | Image.Image, layout: dict[str, Any] | list[dict[str, Any]], values: dict[str, str | None], *, fmt: str = "PNG"
) -> RenderResult:
    """``layout`` is the template JSON (dict) or, for simple templates, the list of fields."""
    spec: dict[str, Any] = {"fields": layout} if isinstance(layout, list) else layout
    if isinstance(base, Path):
        with Image.open(base) as original:  # the original file is only read
            canvas = original.convert("RGBA").copy()
    else:
        canvas = base.convert("RGBA").copy()
    scale = (float(canvas.width), float(canvas.height)) if spec.get("units") == "relative" else None
    fields = spec.get("fields", [])
    resolved = {f["name"]: resolve_value(f, values) for f in fields}
    for f in fields:
        if f.get("required") and not resolved[f["name"]]:
            raise TemplateError(f"Не заполнено обязательное поле «{f['name']}»")
    erase_specs = spec.get("erase", [])
    calibrated: dict[str, dict[str, Any]] = {}
    for raw in fields:
        cal = raw.get("calibrate")
        if cal is not None and resolved[raw["name"]] and 0 <= int(cal.get("erase", -1)) < len(erase_specs):
            found = calibrate(canvas, raw, erase_specs[int(cal["erase"])], scale)
            if found is not None:
                calibrated[raw["name"]] = found
    for area in erase_specs:
        only_if = area.get("when")
        if only_if and not resolved.get(only_if):
            continue
        erase(canvas, area, scale)
    layouts: dict[str, Layout] = {}
    skipped: list[str] = []
    for raw in fields:
        f = TextField.from_spec(calibrated[raw["name"]], None) if raw["name"] in calibrated else TextField.from_spec(raw, scale)
        value = supported_text(resolved[f.name], f.font)
        if not value:
            skipped.append(f.name)
            continue
        layout_ = fit_text(value, f)
        layouts[f.name] = layout_
        _draw_lines(canvas, f, layout_)
    buffer = io.BytesIO()
    out = canvas if fmt.upper() == "PNG" else canvas.convert("RGB")
    out.save(buffer, format=fmt.upper(), optimize=True)
    data = buffer.getvalue()
    return RenderResult(data, canvas.width, canvas.height, hashlib.sha256(data).hexdigest(), layouts, skipped)


def analyze(path: Path, colors: int = 6) -> dict[str, Any]:
    """Size, format and dominant palette of a template image."""
    with Image.open(path) as img:
        info = {"width": img.width, "height": img.height, "format": img.format, "mode": img.mode}
        small = img.convert("RGB").copy()
    small.thumbnail((200, 200))
    quant = small.quantize(colors=colors)
    palette = quant.getpalette() or []
    counts = sorted(quant.getcolors() or [], reverse=True)
    info["palette"] = [
        {"hex": "#{:02X}{:02X}{:02X}".format(*palette[idx * 3 : idx * 3 + 3]), "share": round(cnt / (small.width * small.height), 3)}
        for cnt, idx in counts[:colors]
    ]
    return info
