"""Image generator: Cyrillic, long names, optional fields, emoji, originals kept
intact, erasing baked-in text with calibration, template registry."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from autocommerce.config import get_settings
from autocommerce.database.session import get_sessionmaker, session_scope
from autocommerce.imaging import generator, templates
from autocommerce.services import catalog

from .factories import make_product

ORIGINALS = templates.templates_dir() / "originals"


def test_cyrillic_long_names_and_optional_fields():
    templates.ensure_demo_files()
    spec = templates.DEMO_LAYOUTS["demo-graphite"]
    base = templates.templates_dir() / "demo" / "demo-graphite.png"
    long_name = "Подарочная карта PlayStation Store для аккаунтов Турции с очень-очень длинным названием, которое не помещается " * 2
    result = generator.render(base, spec["fields"], {"title": long_name, "category": "Подарочные карты", "nominal": "1000 TRY ⭐🔥"})
    title = result.layouts["title"]
    assert title.truncated and title.lines[-1].endswith("…") and len(title.lines) <= 3
    assert result.layouts["nominal"].lines == ["1000 TRY"]  # emoji the font cannot draw are dropped
    assert {"region", "price", "subtitle"} <= set(result.skipped)
    with pytest.raises(generator.TemplateError):
        generator.render(base, spec["fields"], {"title": ""})  # required field


def test_original_file_is_never_modified(tmp_path):
    original = tmp_path / "orig.png"
    Image.new("RGB", (400, 300), (40, 90, 200)).save(original)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    generator.render(original, [{"name": "title", "box": [10, 10, 380, 100], "size": 40}], {"title": "Тест"})
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before


def _mock_template(path: Path) -> None:
    """A stand-in for the owner's Stars template: gradient + white «50» / «звёзд»."""
    w, h = 992, 744
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line((0, y, w, y), fill=(50, 140 + y // 12, 230))
    font = ImageFont.truetype(str(get_settings().assets_dir / "fonts" / "Unbounded-VF.ttf"), 142)
    font.set_variation_by_name("Bold")
    small = ImageFont.truetype(str(get_settings().assets_dir / "fonts" / "Unbounded-VF.ttf"), 56)
    small.set_variation_by_name("Bold")
    d.text((55, 506), "50", font=font, fill="white", anchor="ls")
    d.text((55, 585), "звёзд", font=small, fill="white", anchor="ls")
    img.save(path)


def _white_bbox(img: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    region = img.crop(box)
    return generator.text_mask(region, 205, 70, dilate=0).getbbox()


def test_baked_text_is_erased_and_new_text_is_calibrated(tmp_path):
    base = tmp_path / "tg-stars.png"
    _mock_template(base)
    spec = json.loads((ORIGINALS / "tg-stars.json").read_text())
    orig = Image.open(base).convert("RGB")
    before = _white_bbox(orig, (0, 360, 600, 520))
    result = generator.render(base, spec, {"amount": "101", "amount_word": "звезда"})
    out = Image.open(__import__("io").BytesIO(result.data)).convert("RGB")
    after = _white_bbox(out, (0, 360, 600, 520))
    assert before and after
    # same left edge and cap height as the original lettering (±3 px)
    assert abs(after[0] - before[0]) <= 3
    assert abs((after[3] - after[1]) - (before[3] - before[1])) <= 3
    # nothing of the old «50» remains to the right of the new, narrower number
    old_right_area = _white_bbox(out, (55 + (after[2] - after[0]) + 20, 360, 600, 520))
    assert old_right_area is None or (old_right_area[2] - old_right_area[0]) < 5
    assert result.layouts["amount_word"].lines == ["звезда"]


async def test_registry_waits_for_owner_files_then_activates(tmp_path):
    async with session_scope() as s:
        stats = await templates.sync_registry(s)
    assert stats["awaiting_file"] >= 5
    async with get_sessionmaker()() as s:
        rows = {t.code: t for t in await templates.list_templates(s)}
    assert not rows["user-tg-premium"].active and templates.template_state(rows["user-tg-premium"]) == "awaiting_file"
    # the owner drops the PNG: the template becomes active and wins for its category
    target = ORIGINALS / "tg-stars.png"
    _mock_template(target)
    try:
        async with session_scope() as s:
            await templates.sync_registry(s)
            await __import__("autocommerce.services.bootstrap", fromlist=["seed"]).seed(s)
        pid = await make_product(
            name="Telegram Stars 1000", category="tg_stars", manual_cost="1200", face_value="1000", face_currency="STARS"
        )
        async with session_scope() as s:
            product = await catalog.get_product(s, pid)
            tpl = await templates.pick_template(s, product)
            assert tpl.code == "user-tg-stars"
            values = templates.values_for(product)
            assert values["amount"] == "1000" and values["amount_word"] == "звёзд"
            image = await templates.generate_for_product(s, product, preview=True)
            assert templates.image_path(image).exists() and image.template_code == "user-tg-stars"
    finally:
        target.unlink(missing_ok=True)
        shutil.rmtree(get_settings().storage_dir / "images", ignore_errors=True)


def test_russian_plurals():
    forms = templates.AMOUNT_WORDS["STARS"]
    assert [templates.plural_ru(n, forms) for n in (1, 2, 5, 11, 21, 50, 101, 1000)] == [
        "звезда",
        "звезды",
        "звёзд",
        "звёзд",
        "звезда",
        "звёзд",
        "звезда",
        "звёзд",
    ]
    months = templates.AMOUNT_WORDS["MONTHS"]
    assert [templates.plural_ru(n, months) for n in (3, 6, 12)] == ["месяца", "месяцев", "месяцев"]
