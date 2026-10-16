from __future__ import annotations

from datetime import timedelta

import pytest

from nft_gift_bot.config.settings import Settings
from nft_gift_bot.models import SubscriptionStatus
from nft_gift_bot.services.settings_service import SettingsService
from nft_gift_bot.services.subscription_service import SubscriptionService
from tests.conftest import NOW, make_user


async def test_renewal_stacks_on_active_subscription(session) -> None:
    user = await make_user(session)
    service = SubscriptionService(session)
    await service.extend(user.id, 30, NOW)
    sub = await service.extend(user.id, 30, NOW + timedelta(days=10))
    assert sub.expires_at == NOW + timedelta(days=60)


async def test_renewal_after_expiry_starts_from_now(session) -> None:
    user = await make_user(session)
    service = SubscriptionService(session)
    await service.extend(user.id, 30, NOW)
    later = NOW + timedelta(days=40)
    expired = await service.expire_due(later)
    assert [s.user_id for s in expired] == [user.id]
    assert expired[0].status == SubscriptionStatus.EXPIRED
    assert not await service.is_active(user.id, later)
    sub = await service.extend(user.id, 30, later)
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.starts_at == later
    assert sub.expires_at == later + timedelta(days=30)


async def test_expiry_warning_sent_once(session) -> None:
    user = await make_user(session)
    service = SubscriptionService(session)
    await service.extend(user.id, 2, NOW)
    window = timedelta(hours=72)
    assert len(await service.take_expiry_warnings(NOW, window)) == 1
    await session.flush()
    assert await service.take_expiry_warnings(NOW, window) == []
    await service.extend(user.id, 30, NOW)  # renewal resets the warning flag
    await session.flush()
    assert await service.take_expiry_warnings(NOW + timedelta(days=30), window) != []


async def test_admin_price_and_term_overrides(session) -> None:
    cfg = SettingsService(session, Settings(_env_file=None))
    assert await cfg.subscription_price_nano() == 10 * 10**9
    assert await cfg.subscription_days() == 30
    await cfg.set_subscription_price("12.5", admin_id=1)
    await cfg.set_subscription_days("90", admin_id=1)
    assert await cfg.subscription_price_nano() == 12_500_000_000
    assert await cfg.subscription_days() == 90
    for bad in ("0", "-5", "x"):
        with pytest.raises((ValueError, ArithmeticError)):
            await cfg.set_subscription_price(bad, admin_id=1)
    for bad in ("0", "abc", "99999"):
        with pytest.raises(ValueError):
            await cfg.set_subscription_days(bad, admin_id=1)
