import re
from pathlib import Path

import pytest

from gift_parser.parser import parse_gift_html, parse_gift_ref

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_gift_page():
    html = (FIXTURES / "gift.html").read_text(encoding="utf-8")
    gift = parse_gift_html(html, "PlushPepe", 7)

    assert gift is not None
    assert gift.url == "https://t.me/nft/PlushPepe-7"
    assert gift.title == "Plush Pepe #7"
    assert gift.owner_name == "Some User"
    assert gift.owner_link == "https://t.me/someuser"
    assert (gift.model.name, gift.model.rarity) == ("Pumpkin Pepe", 0.5)
    assert (gift.backdrop.name, gift.backdrop.rarity) == ("Black", 1.2)
    assert (gift.symbol.name, gift.symbol.rarity) == ("Crown", 0.3)
    assert (gift.issued, gift.total) == (2838, 2838)
    assert gift.to_flat_dict()["model_rarity"] == 0.5


def test_missing_gift_returns_none():
    html = (FIXTURES / "missing.html").read_text(encoding="utf-8")
    assert parse_gift_html(html, "PlushPepe", 999999) is None


@pytest.mark.parametrize("ref, expected", [
    ("https://t.me/nft/PlushPepe-12", ("PlushPepe", 12)),
    ("t.me/nft/DurovsCap-1", ("DurovsCap", 1)),
    ("SnoopDogg-305", ("SnoopDogg", 305)),
])
def test_parse_gift_ref(ref, expected):
    assert parse_gift_ref(ref) == expected


def test_parse_gift_ref_invalid():
    with pytest.raises(ValueError):
        parse_gift_ref("not a link")


GIFT_TEMPLATE = (FIXTURES / "gift.html").read_text(encoding="utf-8")


def _localized(owner, model, backdrop, symbol, quantity):
    html = GIFT_TEMPLATE
    for en, loc in [("Owner", owner), ("Model", model), ("Backdrop", backdrop),
                    ("Symbol", symbol), ("Quantity", quantity)]:
        html = html.replace(f"<th>{en}</th>", f"<th>{loc}</th>")
    return html


@pytest.mark.parametrize("labels", [
    ("所有者", "モデル", "背景", "シンボル", "数量"),           # японский
    ("소유자", "모델", "배경", "심볼", "수량"),                 # корейский
    ("拥有者", "模型", "背景", "图案", "数量"),                 # китайский
    ("Владелец", "Модель", "Фон", "Узор", "Количество"),      # русский
    ("Besitzer", "Modell", "Hintergrund", "Symbol", "Anzahl"),  # немецкий
    ("Xx", "Yy", "Zz", "Ww", "Vv"),                           # незнакомый язык
])
def test_parse_localized_page(labels):
    gift = parse_gift_html(_localized(*labels), "PlushPepe", 7)
    assert gift is not None
    assert gift.owner_name == "Some User"
    assert (gift.model.name, gift.backdrop.name, gift.symbol.name) == ("Pumpkin Pepe", "Black", "Crown")
    assert (gift.issued, gift.total) == (2838, 2838)
    assert gift.extra == {}


def test_catalog():
    from gift_parser.catalog import COLLECTIONS, find, latest

    slugs = [s for s, _ in COLLECTIONS]
    assert len(slugs) == len(set(slugs))
    assert all(re.fullmatch(r"[A-Za-z0-9]+", s) for s in slugs)
    assert latest(3) == COLLECTIONS[:3]
    assert ("PlushPepe", "Plush Pepe") in find("plush pepe")


def test_bot_texts_complete():
    from texts import TEXTS, t

    for lang, texts in TEXTS.items():
        assert texts.keys() == TEXTS["ru"].keys(), lang
        t(lang, "start", max=500)
        t(lang, "parsing", slug="PlushPepe", start=1, end=2)
        t(lang, "found_of", n=1, total=2)
    assert t("de", "not_found") == TEXTS["en"]["not_found"]


@pytest.mark.parametrize("name, lang", [
    ("김민준", "ko"),
    ("たなか", "ja"),
    ("田中 さくら", "ja"),
    ("タナカ", "ja"),
    ("王伟", "zh"),
    ("محمد", "ar"),
    ("Иван Петров", "ru"),
    ("Олексій Їжак", "uk"),
    ("John 🎁", "latin"),
    ("🎁🎁", None),
    (None, None),
])
def test_detect_owner_lang(name, lang):
    from gift_parser.owner_lang import detect_owner_lang

    assert detect_owner_lang(name) == lang


def test_owner_lang_in_csv():
    html = (FIXTURES / "gift.html").read_text(encoding="utf-8").replace("Some User", "김민준")
    gift = parse_gift_html(html, "PlushPepe", 7)
    assert gift.owner_lang == "ko"
    assert gift.to_flat_dict()["owner_lang"] == "ko"
    assert gift.to_dict()["owner_lang"] == "ko"
