from __future__ import annotations

from datetime import timedelta

import pytest

from nft_gift_bot.gifts.api import GiftApiError
from nft_gift_bot.gifts.intent import parse_transfer_intent
from nft_gift_bot.gifts.recipient import RecipientRef, parse_recipient
from nft_gift_bot.gifts.service import GiftAccessError, GiftService
from nft_gift_bot.models import TransferStatus
from tests.conftest import NOW, FakeGiftApi, connect, later, make_user, subscribe, unique_gift

TTL = timedelta(minutes=5)
ALICE = RecipientRef(username="alice")


async def _ready(session, box, api, **rights):
    user = await make_user(session)
    await subscribe(session, user)
    await connect(session, box, user, **rights)
    service = GiftService(session, api, box)
    gifts = await service.refresh_gifts(user.id, NOW) if rights.get("view", True) else []
    return user, service, gifts


def test_parse_recipient() -> None:
    assert parse_recipient("@alice_1") == RecipientRef(username="alice_1")
    assert parse_recipient("https://t.me/alice_1") == RecipientRef(username="alice_1")
    assert parse_recipient("123456789") == RecipientRef(user_id=123456789)
    for bad in ("", "@a", "hello world", "@some_bot", "12", "@1abc", "<script>"):
        assert parse_recipient(bad) is None


def test_parse_intent() -> None:
    intent = parse_transfer_intent("Передай подарок Plush Pepe #12 пользователю @alice")
    assert intent.gift_query == "Plush Pepe #12"
    assert intent.recipient == ALICE
    assert parse_transfer_intent("/transfer 3 123456789").gift_query == "3"
    assert parse_transfer_intent("привет") is None
    assert parse_transfer_intent("передай @alice") is None


async def test_full_confirmed_transfer(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()])
    user, service, gifts = await _ready(session, box, api)
    preview = await service.prepare_transfer(user.id, gifts[0].id, ALICE, NOW, TTL)
    assert preview.transfer.status == TransferStatus.PENDING_CONFIRMATION
    assert preview.transfer.star_count == 25
    assert api.transfers == []  # nothing happens before confirmation

    transfer = await service.confirm(user.id, preview.transfer.id, later(1))
    assert transfer.status == TransferStatus.SUCCEEDED
    assert api.transfers == [("bc-secret-1", "og-1", 2002, 25)]


async def test_double_confirm_executes_once(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()])
    user, service, gifts = await _ready(session, box, api)
    preview = await service.prepare_transfer(user.id, gifts[0].id, ALICE, NOW, TTL)
    await service.confirm(user.id, preview.transfer.id, later(1))
    with pytest.raises(GiftAccessError) as exc:
        await service.confirm(user.id, preview.transfer.id, later(1))
    assert exc.value.code == "already_processed"
    assert len(api.transfers) == 1


async def test_confirmation_expires(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()])
    user, service, gifts = await _ready(session, box, api)
    preview = await service.prepare_transfer(user.id, gifts[0].id, ALICE, NOW, TTL)
    with pytest.raises(GiftAccessError) as exc:
        await service.confirm(user.id, preview.transfer.id, later(6))
    assert exc.value.code == "confirmation_expired"
    assert preview.transfer.status == TransferStatus.EXPIRED
    assert api.transfers == []


async def test_cancelled_transfer_cannot_be_confirmed(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()])
    user, service, gifts = await _ready(session, box, api)
    preview = await service.prepare_transfer(user.id, gifts[0].id, ALICE, NOW, TTL)
    assert await service.cancel(user.id, preview.transfer.id)
    with pytest.raises(GiftAccessError):
        await service.confirm(user.id, preview.transfer.id, later(1))
    assert api.transfers == []


async def test_api_error_recorded_not_faked(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()], transfer_error=GiftApiError("network", "Сетевая ошибка"))
    user, service, gifts = await _ready(session, box, api)
    preview = await service.prepare_transfer(user.id, gifts[0].id, ALICE, NOW, TTL)
    transfer = await service.confirm(user.id, preview.transfer.id, later(1))
    assert transfer.status == TransferStatus.FAILED
    assert transfer.error_code == "network"
    history = await service.history(user.id)
    assert [t.status for t in history] == [TransferStatus.FAILED]


@pytest.mark.parametrize(
    ("gift_kwargs", "code"),
    [
        ({"can_be_transferred": False}, "not_transferable"),
        ({"next_transfer_date": NOW + timedelta(days=3)}, "too_early"),
    ],
)
async def test_transfer_preconditions(session, box, gift_kwargs, code) -> None:
    api = FakeGiftApi(gifts=[unique_gift(**gift_kwargs)])
    user, service, gifts = await _ready(session, box, api)
    with pytest.raises(GiftAccessError) as exc:
        await service.prepare_transfer(user.id, gifts[0].id, ALICE, NOW, TTL)
    assert exc.value.code == code


async def test_recipient_checks(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()], known_users={"alice": 2002, "me": 1001})
    user, service, gifts = await _ready(session, box, api)
    with pytest.raises(GiftAccessError) as exc:
        await service.prepare_transfer(user.id, gifts[0].id, RecipientRef(username="ghost"), NOW, TTL)
    assert exc.value.code == "recipient_error"
    with pytest.raises(GiftAccessError) as exc:
        await service.prepare_transfer(user.id, gifts[0].id, RecipientRef(username="me"), NOW, TTL)
    assert exc.value.code == "self_transfer"


async def test_missing_rights_block_operations(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift()])
    user, service, _ = await _ready(session, box, api, view=False)
    with pytest.raises(GiftAccessError) as exc:
        await service.refresh_gifts(user.id, NOW)
    assert exc.value.code == "no_view_right"


async def test_paid_transfer_needs_stars_right(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift(fee=25)])
    user, service, gifts = await _ready(session, box, api, stars=False)
    with pytest.raises(GiftAccessError) as exc:
        await service.prepare_transfer(user.id, gifts[0].id, ALICE, NOW, TTL)
    assert exc.value.code == "no_stars_right"


async def test_gift_list_sync_removes_gone_gifts(session, box) -> None:
    api = FakeGiftApi(gifts=[unique_gift("a", "A #1"), unique_gift("b", "B #2")])
    user, service, gifts = await _ready(session, box, api)
    assert {g.owned_gift_id for g in gifts} == {"a", "b"}
    api.gifts = [unique_gift("b", "B #2")]
    assert [g.owned_gift_id for g in await service.refresh_gifts(user.id, NOW)] == ["b"]
    assert [g.title for g in await service.find_gifts(user.id, "#2", NOW)] == ["B #2"]
