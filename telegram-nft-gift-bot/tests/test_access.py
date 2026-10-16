"""Authorization: admins by ID only, owners only touch their own data."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from nft_gift_bot.admin.guards import AdminFilter, is_admin
from nft_gift_bot.admin.service import AdminService
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.gifts.recipient import RecipientRef
from nft_gift_bot.gifts.service import GiftAccessError, GiftService
from nft_gift_bot.models import AdminAction, ConnectionStatus
from nft_gift_bot.telegram_accounts.service import (
    AccountConnectionService,
    BusinessConnectionEvent,
    ConnectionOutcome,
)
from tests.conftest import NOW, FakeGiftApi, connect, make_user, subscribe, unique_gift


def test_admin_ids_parsing() -> None:
    assert Settings(_env_file=None, admin_ids="1, 22,333").admin_id_set == frozenset({1, 22, 333})
    assert Settings(_env_file=None, admin_ids="").admin_id_set == frozenset()
    with pytest.raises(ValueError):
        _ = Settings(_env_file=None, admin_ids="@admin").admin_id_set


async def test_admin_filter_uses_numeric_id_only() -> None:
    f = AdminFilter(frozenset({42}))
    assert await f(SimpleNamespace(from_user=SimpleNamespace(id=42, username="anyone")))
    assert not await f(SimpleNamespace(from_user=SimpleNamespace(id=7, username="admin")))
    assert not await f(SimpleNamespace(from_user=None))
    assert not is_admin(None, frozenset({42}))


async def test_admin_actions_are_audited(session) -> None:
    await make_user(session, 555)
    service = AdminService(session, Settings(_env_file=None), admin_telegram_id=42)
    await service.set_price("15")
    await service.grant_subscription(555, 7, NOW)
    await service.user_card(555)
    await session.flush()
    rows = (await session.scalars(select(AdminAction).order_by(AdminAction.id))).all()
    assert [r.action for r in rows] == ["set_subscription_price", "grant_subscription", "view_user"]
    assert all(r.admin_telegram_id == 42 for r in rows)


async def test_connection_requires_known_user_and_subscription(session, box) -> None:
    service = AccountConnectionService(session, box)
    event = BusinessConnectionEvent("bc-x", 777, True, True, True, True)
    assert (await service.handle_event(event, NOW)).outcome is ConnectionOutcome.UNKNOWN_USER
    user = await make_user(session, 777)
    assert (await service.handle_event(event, NOW)).outcome is ConnectionOutcome.NO_SUBSCRIPTION
    await subscribe(session, user)
    result = await service.handle_event(event, NOW)
    assert result.outcome is ConnectionOutcome.CONNECTED
    # Stored encrypted, never in plain text.
    assert "bc-x" not in result.account.connection_id_encrypted
    assert service.connection_id(result.account) == "bc-x"


async def test_disable_and_revoke(session, box) -> None:
    user = await make_user(session)
    await subscribe(session, user)
    await connect(session, box, user)
    service = AccountConnectionService(session, box)
    off = BusinessConnectionEvent("bc-secret-1", user.telegram_id, False, True, True, True)
    assert (await service.handle_event(off, NOW)).outcome is ConnectionOutcome.DISABLED
    on = BusinessConnectionEvent("bc-secret-1", user.telegram_id, True, True, True, True)
    assert (await service.handle_event(on, NOW)).outcome is ConnectionOutcome.UPDATED

    assert await service.revoke(user.id, NOW)
    account = await service.get_latest(user.id)
    assert account.status == ConnectionStatus.REVOKED
    assert account.connection_id_encrypted == ""
    assert await service.get_active(user.id) is None


async def test_user_cannot_touch_other_users_gifts_or_transfers(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()])
    owner = await make_user(session, 1001)
    await subscribe(session, owner)
    await connect(session, box, owner)
    owner_gifts = await GiftService(session, api, box).refresh_gifts(owner.id, NOW)
    preview = await GiftService(session, api, box).prepare_transfer(
        owner.id, owner_gifts[0].id, RecipientRef(username="alice"), NOW, timedelta(minutes=5)
    )

    intruder = await make_user(session, 3003, "intruder")
    await subscribe(session, intruder)
    await connect(session, box, intruder, connection_id="bc-intruder")
    service = GiftService(session, api, box)
    with pytest.raises(GiftAccessError) as exc:
        await service.get_gift(intruder.id, owner_gifts[0].id, NOW)
    assert exc.value.code == "gift_not_found"
    with pytest.raises(GiftAccessError) as exc:
        await service.confirm(intruder.id, preview.transfer.id, NOW)
    assert exc.value.code == "transfer_not_found"
    assert not await service.cancel(intruder.id, preview.transfer.id)
    assert api.transfers == []


async def test_expired_subscription_blocks_gift_operations(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()])
    user = await make_user(session)
    await subscribe(session, user, days=1)
    await connect(session, box, user)
    service = GiftService(session, api, box)
    gifts = await service.refresh_gifts(user.id, NOW)
    preview = await service.prepare_transfer(user.id, gifts[0].id, RecipientRef(username="alice"), NOW, timedelta(days=2))
    with pytest.raises(GiftAccessError) as exc:
        await service.confirm(user.id, preview.transfer.id, NOW + timedelta(days=1, minutes=1))
    assert exc.value.code == "no_subscription"
    assert api.transfers == []
