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
