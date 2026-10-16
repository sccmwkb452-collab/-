from __future__ import annotations

import logging

from nft_gift_bot.bot.ui import Rich, utf16_len
from nft_gift_bot.config.emoji import is_configured_id, resolve
from nft_gift_bot.config.logging import RedactingFilter
from nft_gift_bot.services.crypto import SecretBox, generate_key, mask
from nft_gift_bot.services.rate_limit import SlidingWindowRateLimiter


def test_encryption_roundtrip_and_lookup_hash() -> None:
    box = SecretBox(generate_key())
    token = box.encrypt("connection-123")
    assert "connection-123" not in token
    assert box.decrypt(token) == "connection-123"
    assert box.lookup_hash("x") == box.lookup_hash("x")
    assert SecretBox(generate_key()).lookup_hash("x") != box.lookup_hash("x")


def test_mask() -> None:
    assert mask(123456789) == "•••••6789"
    assert mask(None) == "—"


def test_rate_limiter() -> None:
    now = [0.0]
    limiter = SlidingWindowRateLimiter(2, 60, clock=lambda: now[0])
    assert limiter.allow(1) and limiter.allow(1)
    assert not limiter.allow(1)
    assert limiter.allow(2)
    now[0] = 61
    assert limiter.allow(1)


def test_log_redaction() -> None:
    f = RedactingFilter(["super-secret-key"])
    record = logging.makeLogRecord(
        {"msg": "token 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ key super-secret-key url?api_key=abc", "args": None}
    )
    f.filter(record)
    assert "AAHdqTcv" not in record.msg
    assert "super-secret-key" not in record.msg
    assert "api_key=***" in record.msg


def test_demo_emoji_ids_fall_back_to_unicode() -> None:
    assert not is_configured_id("DEMO_GIFT")
    assert not is_configured_id("")
    assert not is_configured_id("0")
    assert is_configured_id("5368324170671202286")
    rich = Rich().e("gift").t(" Подарки")
    assert rich.text == "🎁 Подарки"
    assert rich.entities == []


def test_custom_emoji_entity_offsets_are_utf16() -> None:
    rich = Rich({"gift": "5368324170671202286"}).t("💎 a ").e("gift").b("Bold")
    entity = rich.entities[0]
    assert entity.type == "custom_emoji"
    assert entity.custom_emoji_id == "5368324170671202286"
    assert entity.offset == utf16_len("💎 a ") == 5
    assert entity.length == 2
    assert rich.entities[1].offset == 7
    assert resolve("gift", {"gift": "-"}).custom_id == "-"
