"""End-to-end: real aiogram Dispatcher + handlers, fake Telegram transport, fake TON chain."""

from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, SendMessage, TelegramMethod
from aiogram.types import (
    BusinessBotRights,
    BusinessConnection,
    CallbackQuery,
    Chat,
    Message,
    Update,
)
from aiogram.types import (
    User as TgUser,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from nft_gift_bot.bot.factory import build_dispatcher
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.database.base import Base
from nft_gift_bot.keyboards.callbacks import GiftCb, SubCb
from nft_gift_bot.keyboards.main import MENU_GIFTS, MENU_SUBSCRIPTION
from nft_gift_bot.models import GiftTransfer, Payment
from nft_gift_bot.payments.verifier import IncomingTransfer
from nft_gift_bot.services.crypto import SecretBox, generate_key
from tests.conftest import FakeChain, FakeGiftApi, unique_gift

OWNER = 1001
ADMIN = 9


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[TelegramMethod] = []
        self._ids = itertools.count(100)

    async def make_request(self, bot, method, timeout=None):  # noqa: ANN001
        self.sent.append(method)
        if isinstance(method, GetMe):
            return TgUser(id=42, is_bot=True, first_name="Bot", username="nft_gift_test_bot")
        if isinstance(method, SendMessage):
            return Message(message_id=next(self._ids), date=datetime.now(timezone.utc),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError

    def texts(self) -> list[str]:
        return [m.text for m in self.sent if isinstance(m, SendMessage)]


class Harness:
    def __init__(self, dp, bot, session_rec, factory, chain, api) -> None:  # noqa: ANN001
        self.dp, self.bot, self.rec, self.factory, self.chain, self.api = dp, bot, session_rec, factory, chain, api
        self._update_ids = itertools.count(1)

    def _user(self, uid: int) -> TgUser:
        return TgUser(id=uid, is_bot=False, first_name="U", username=f"user{uid}")

    def _msg(self, uid: int, text: str) -> Message:
        return Message(message_id=next(self._update_ids), date=datetime.now(timezone.utc),
                       chat=Chat(id=uid, type="private"), from_user=self._user(uid), text=text)

    async def text(self, text: str, uid: int = OWNER) -> list[str]:
        before = len(self.rec.texts())
        await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), message=self._msg(uid, text)))
        return self.rec.texts()[before:]

    async def tap(self, data: str, uid: int = OWNER) -> list[str]:
        before = len(self.rec.texts())
        cb = CallbackQuery(id=str(next(self._update_ids)), from_user=self._user(uid), chat_instance="ci",
                           data=data, message=self._msg(uid, "prev"))
        await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), callback_query=cb))
        return self.rec.texts()[before:]

    async def connect_business(self, uid: int = OWNER) -> list[str]:
        before = len(self.rec.texts())
        conn = BusinessConnection(
            id="bc-live-1", user=self._user(uid), user_chat_id=uid, date=datetime.now(timezone.utc), is_enabled=True,
            rights=BusinessBotRights(can_view_gifts_and_stars=True, can_transfer_and_upgrade_gifts=True, can_transfer_stars=True),
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), business_connection=conn))
        return self.rec.texts()[before:]


class _Proxy:
    """Routers are module-level singletons (attachable once), so the dispatcher is built once
    and per-test state (DB, fake chain, fake gift API) is swapped behind these proxies."""

    def __init__(self) -> None:
        self.target = None

    def __call__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self.target(*args, **kwargs)

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(self.target, name)


KEY = generate_key()
SETTINGS = Settings(_env_file=None, admin_ids=str(ADMIN), ton_receiver_address="UQ-test-receiver",
                    bot_token="42:TEST", encryption_key=KEY, rate_limit_per_minute=1000)
FACTORY, CHAIN, API = _Proxy(), _Proxy(), _Proxy()
DP = build_dispatcher(SETTINGS, FACTORY, SecretBox(KEY), CHAIN, API)


@pytest_asyncio.fixture
async def harness():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    FACTORY.target = async_sessionmaker(engine, expire_on_commit=False)
    CHAIN.target = FakeChain()
    API.target = FakeGiftApi(gifts=[unique_gift()])
    DP.storage.storage.clear()
    rec = RecordingSession()
    bot = Bot("42:TEST", session=rec)
    yield Harness(DP, bot, rec, FACTORY.target, CHAIN.target, API.target)
    await engine.dispose()


async def test_full_user_journey(harness: Harness) -> None:
    assert "Добро пожаловать в NFT Gift Manager" in (await harness.text("/start"))[0]
    assert "10 TON" in (await harness.text(MENU_SUBSCRIPTION))[0]

    invoice = (await harness.tap(SubCb(action="buy").pack()))[0]
    async with harness.factory() as s:
        payment = await s.scalar(select(Payment))
    assert payment.memo in invoice

    # "I paid" without a real transaction does nothing.
    assert await harness.tap(SubCb(action="check", payment_id=payment.id).pack()) == []
    harness.chain.transfers.append(IncomingTransfer("tx1", "0:payer", payment.amount_nano, payment.memo,
                                                    int(datetime.now(timezone.utc).timestamp())))
    confirmed = await harness.tap(SubCb(action="check", payment_id=payment.id).pack())
    assert any("Оплата подтверждена" in t for t in confirmed)

    assert "Аккаунт подключён" in (await harness.connect_business())[0]
    gift_list = (await harness.text(MENU_GIFTS))[0]
    assert "Plush Pepe #12" in gift_list

    preview = (await harness.text("передай Plush Pepe @alice"))[0]
    assert "Подтвердите передачу" in preview and "25 ⭐" in preview
    assert harness.api.transfers == []

    async with harness.factory() as s:
        transfer = await s.scalar(select(GiftTransfer))
    result = await harness.tap(GiftCb(action="confirm", id=transfer.id).pack())
    assert "Подарок передан" in result[0]
    assert harness.api.transfers == [("bc-live-1", "og-1", 2002, 25)]

    # Replayed confirmation does not transfer again.
    await harness.tap(GiftCb(action="confirm", id=transfer.id).pack())
    assert len(harness.api.transfers) == 1


async def test_business_connection_without_subscription_is_rejected(harness: Harness) -> None:
    await harness.text("/start")
    assert "Подключение не активировано" in (await harness.connect_business())[0]
    assert "Нужна активная подписка" in (await harness.text(MENU_GIFTS))[0]


async def test_admin_panel_only_for_admin_ids(harness: Harness) -> None:
    assert "Статистика" in (await harness.text("/admin", uid=ADMIN))[0]
    stranger = await harness.text("/admin", uid=OWNER)
    assert stranger and "Статистика" not in stranger[0]
    assert "Формат" in (await harness.text("/set_price abc", uid=ADMIN))[0]
    assert "15 TON" in (await harness.text("/set_price 15", uid=ADMIN))[0]
    assert "15 TON" in (await harness.text("/start", uid=OWNER))[0]


async def test_transfer_command_with_nft_link(harness: Harness) -> None:
    await harness.text("/start")
    async with harness.factory() as s:
        from nft_gift_bot.models import User as DbUser
        from nft_gift_bot.services.subscription_service import SubscriptionService
        user = await s.scalar(select(DbUser))
        await SubscriptionService(s).extend(user.id, 30, datetime.now(timezone.utc))
        await s.commit()
    await harness.connect_business()
    await harness.text(MENU_GIFTS)

    missing = (await harness.text("/transfer https://t.me/nft/DurovCap-7 @alice"))[0]
    assert "не найден на вашем подключённом аккаунте" in missing

    preview = (await harness.text("/transfer https://t.me/nft/PlushPepe-12 @alice"))[0]
    assert "Подтвердите передачу" in preview and "@alice" in preview
    assert harness.api.transfers == []
    async with harness.factory() as s:
        transfer = await s.scalar(select(GiftTransfer))
    assert "Подарок передан" in (await harness.tap(GiftCb(action="confirm", id=transfer.id).pack()))[0]
    assert harness.api.transfers == [("bc-live-1", "og-1", 2002, 25)]

    assert "Формат" in (await harness.text("/transfer"))[0]
