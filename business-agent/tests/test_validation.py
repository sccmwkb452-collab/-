from decimal import Decimal

from app.ai.validation import (
    check_outgoing_text,
    currency_mentioned,
    detect_opt_out,
    extract_numbers,
    find_bot_mentions,
    price_mentioned,
)
from app.core.redaction import redact, redact_text


def test_numbers_and_prices():
    assert Decimal("1500") in extract_numbers("отдам за 1 500 тон")
    assert Decimal("12.5") in extract_numbers("цена 12,5")
    assert Decimal("2000") in extract_numbers("2к")
    assert price_mentioned("12.50", ["могу за 12,5 TON"])
    assert not price_mentioned("13", ["могу за 12,5 TON"])


def test_currency_mentioned():
    assert currency_mentioned("TON", ["давай за 10 тонов"])
    assert currency_mentioned("XTR", ["500 звёзд"])
    assert not currency_mentioned("USDT", ["давай за 10 тонов"])


def test_opt_out():
    assert detect_opt_out("Больше не пишите мне")
    assert detect_opt_out("стоп")
    assert not detect_opt_out("стопка подарков есть?")


def test_foreign_bots_and_links_blocked():
    assert find_bot_mentions("плати через @fake_garant_bot или t.me/OtherBot") == {"fake_garant_bot", "otherbot"}
    check = check_outgoing_text("Давайте через @fake_garant_bot", allowed_bot_usernames={"cryptobot"},
                                deal_created=False, deal_paid=False)
    assert not check.ok
    ok = check_outgoing_text("Оплата через @CryptoBot", allowed_bot_usernames={"cryptobot"}, deal_created=False, deal_paid=False)
    assert ok.ok
    link = check_outgoing_text("смотри https://evil.example/pay", allowed_bot_usernames=set(), deal_created=False, deal_paid=False)
    assert not link.ok


def test_completion_claims_require_real_deal():
    bad = check_outgoing_text("Сделка создана, ждите", allowed_bot_usernames=set(), deal_created=False, deal_paid=False)
    assert not bad.ok
    good = check_outgoing_text("Сделка создана, ждите", allowed_bot_usernames=set(), deal_created=True, deal_paid=False)
    assert good.ok
    assert check_outgoing_text("Сделка будет создана после согласования", allowed_bot_usernames=set(),
                               deal_created=False, deal_paid=False).ok


def test_redaction():
    text = "token=123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ seed: abandon"
    red = redact_text(text)
    assert "AAHdq" not in red
    phrase = " ".join(["abandon"] * 12)
    assert "abandon abandon" not in redact_text(phrase)
    assert redact({"api_key": "x", "nested": {"password": "y"}}) == {"api_key": "[redacted]", "nested": {"password": "[redacted]"}}
