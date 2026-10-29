import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("ADMIN_IDS", "8790784360")

from app.config import Settings  # noqa: E402
from app.db.models import (  # noqa: E402
    BusinessConnectionRecord,
    Contact,
    Conversation,
    Owner,
    TradeBotConfig,
)
from app.db.session import create_schema, dispose_engine, init_engine  # noqa: E402
from app.trading.base import AvailabilityResult, Capability, OpResult, OpStatus, TradeBotAdapter  # noqa: E402

ADMIN_ID = 8790784360
OWNER_TG = 111


@pytest.fixture
async def sessions(tmp_path):
    """SQLite по умолчанию; TEST_DATABASE_URL=postgresql+asyncpg://… — прогон на PostgreSQL."""
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/test.db"
    factory = init_engine(url)
    if url.startswith("postgresql"):
        from app.db.models import Base
        from app.db.session import _engine

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await create_schema()
    yield factory
    await dispose_engine()


@pytest.fixture
def settings():
    return Settings(bot_token="1:x", ADMIN_IDS=str(ADMIN_ID), ALLOWED_USER_IDS=str(OWNER_TG), _env_file=None)


@pytest.fixture
async def owner(sessions):
    async with sessions() as s:
        o = Owner(telegram_id=OWNER_TG, first_name="Owner", agent_enabled=True)
        s.add(o)
        await s.commit()
        return o


class FakeLLM:
    """Тестовый двойник LLM: возвращает заранее заданные ответы и запоминает запросы."""

    def __init__(self, *responses: dict[str, Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def generate_json(self, *, system, content, schema, effort=None):
        self.calls.append({"system": system, "content": content, "schema": schema, "effort": effort})
        if not self.responses:
            raise AssertionError("FakeLLM: нет ответа")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeAdapter(TradeBotAdapter):
    key = "fake"
    title = "Fake"

    def __init__(self, *, available=True, pay_results=None, status_results=None, caps=None, official=None, manual=False):
        self.available = available
        self.pay_results = list(pay_results or [OpResult(OpStatus.SUCCESS, external_id="t1")])
        self.status_results = list(status_results or [])
        self.caps = caps or [Capability.CHECK, Capability.PAY, Capability.PAYMENT_STATUS, Capability.CREATE_INVOICE,
                             Capability.IDEMPOTENT_PAYMENTS]
        self.official_usernames = official
        self.manual_only = manual
        self.pay_calls: list[str] = []
        self.invoice_calls = 0

    def static_capabilities(self):
        return self.caps

    async def check(self):
        return AvailabilityResult(self.available, self.caps, ["TON", "USDT"], error=None if self.available else "down")

    async def pay(self, req, spend_id):
        self.pay_calls.append(spend_id)
        return self.pay_results.pop(0)

    async def payment_status(self, spend_id, external_id):
        return self.status_results.pop(0) if self.status_results else OpResult(OpStatus.NOT_FOUND)

    async def create_invoice(self, req):
        self.invoice_calls += 1
        return OpResult(OpStatus.SUCCESS, external_id="inv1", url="https://t.me/CryptoBot?start=x")


class FakeFactory:
    def __init__(self, adapter):
        self.adapter = adapter

    def for_config(self, cfg):
        return self.adapter

    def forget(self, cfg_id):
        pass


async def add_trade_bot(s, owner_id, *, username="cryptobot", user_id=1559501630, currencies=("TON",), active=True,
                        verified=True, adapter="cryptopay"):
    cfg = TradeBotConfig(owner_id=owner_id, adapter=adapter, bot_username=username, bot_user_id=user_id,
                         verified_at=datetime.now(timezone.utc) if verified else None, is_active=active,
                         currencies=list(currencies), payment_methods=[], capabilities=[], supported_currencies=[],
                         fee_percent=Decimal("0"), fee_fixed=Decimal("0"))
    s.add(cfg)
    await s.flush()
    return cfg


async def add_conversation(s, owner_id, *, chat_id=555, state=None, rights=None, user_tg=OWNER_TG):
    rec = await s.get(BusinessConnectionRecord, "conn1")
    if rec is None:
        rec = BusinessConnectionRecord(id="conn1", owner_id=owner_id, user_telegram_id=user_tg, user_chat_id=user_tg,
                                       is_enabled=True, allowed=True,
                                       rights=rights if rights is not None else {"can_reply": True, "can_read_messages": True})
        s.add(rec)
    contact = Contact(owner_id=owner_id, telegram_user_id=chat_id, username=f"user{chat_id}", display_name="Seller", profile={})
    s.add(contact)
    await s.flush()
    conv = Conversation(owner_id=owner_id, contact_id=contact.id, business_connection_id=rec.id, chat_id=chat_id,
                        state=state or {}, mode="auto")
    s.add(conv)
    await s.flush()
    return conv


class FakeBot:
    """Минимальный двойник aiogram.Bot для проверки бизнес-логики."""

    def __init__(self):
        self.id = 999
        self.sent: list[dict] = []
        self.deleted: list[dict] = []
        self.delete_error: Exception | None = None
        self.send_error: Exception | None = None
        self._mid = 1000

    async def send_message(self, chat_id, text, business_connection_id=None, reply_markup=None, parse_mode=None, **kw):
        if self.send_error and business_connection_id:
            raise self.send_error
        self._mid += 1
        self.sent.append({"chat_id": chat_id, "text": text, "conn": business_connection_id, "markup": reply_markup})
        return SimpleNamespace(message_id=self._mid)

    async def send_sticker(self, chat_id, sticker, business_connection_id=None, **kw):
        self._mid += 1
        self.sent.append({"chat_id": chat_id, "sticker": sticker, "conn": business_connection_id})
        return SimpleNamespace(message_id=self._mid)

    async def delete_business_messages(self, business_connection_id, message_ids):
        if self.delete_error:
            raise self.delete_error
        self.deleted.append({"conn": business_connection_id, "ids": message_ids})
        return True

    async def get_business_connection(self, connection_id):
        raise RuntimeError("not expected")
