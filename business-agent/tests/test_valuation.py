from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from app.db.models import ExchangeRate, MarketPrice, utcnow
from app.nft.pages import find_gift_links, parse_gift_html
from app.nft.valuation import compare_offer, parse_price_line, valuate

FIX = Path(__file__).parent / "fixtures"


def test_gift_page_parsing():
    page = parse_gift_html((FIX / "gift.html").read_text(), "PlushPepe", 7)
    assert page.model.name == "Pumpkin Pepe" and page.model.rarity_percent == 0.5
    assert page.backdrop.rarity_percent == 1.2 and page.owner_username == "someuser"
    assert page.issued == 2838
    assert parse_gift_html((FIX / "missing.html").read_text(), "PlushPepe", 99999) is None
    assert find_gift_links("вот https://t.me/nft/PlushPepe-7 глянь") == [("PlushPepe", 7)]


def test_price_line():
    row = parse_price_line("PlushPepe sale 15,5 TON model=Pumpkin backdrop=\"Black\" source=Fragment")
    assert row["price"] == Decimal("15.5") and row["model"] == "Pumpkin" and row["backdrop"] == "Black"
    assert row["source"] == "Fragment" and row["kind"] == "sale"
    assert parse_price_line("ерунда") is None


async def test_no_market_data_means_no_estimate(sessions, owner):
    async with sessions() as s:
        val = await valuate(s, owner.id, "PlushPepe", {"model": {"name": "Pumpkin"}})
        assert val.estimate is None and any("оценка невозможна" in w for w in val.warnings)


async def test_estimate_from_comparable_sales_with_conversion(sessions, owner):
    async with sessions() as s:
        for p in ("10", "12", "14"):
            s.add(MarketPrice(owner_id=owner.id, collection="PlushPepe", kind="sale", model="Pumpkin", price=Decimal(p),
                              currency="TON", source="test"))
        s.add(MarketPrice(owner_id=owner.id, collection="PlushPepe", kind="floor", price=Decimal("20"), currency="USDT",
                          source="test", observed_at=utcnow() - timedelta(days=2)))
        s.add(ExchangeRate(source_currency="USDT", target_currency="TON", rate=Decimal("0.5"), provider="t"))
        await s.flush()
        val = await valuate(s, owner.id, "PlushPepe", {"model": {"name": "pumpkin"}}, currency="TON")
        assert val.estimate == Decimal("12") and val.confidence == "medium"
        assert val.floor.price == Decimal("10")  # 20 USDT * 0.5
        assert "ниже" in compare_offer(Decimal("9"), val)


async def test_stale_data_flagged(sessions, owner):
    async with sessions() as s:
        s.add(MarketPrice(owner_id=owner.id, collection="DurovsCap", kind="floor", price=Decimal("100"), currency="TON",
                          source="t", observed_at=utcnow() - timedelta(days=3)))
        await s.flush()
        val = await valuate(s, owner.id, "DurovsCap", {})
        assert val.estimate == Decimal("100") and val.confidence == "low"
        assert any("старше" in w for w in val.warnings)
        assert "Данные обновлены" in val.render()
