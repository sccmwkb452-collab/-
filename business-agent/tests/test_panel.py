"""Сквозная проверка панели: настоящие Dispatcher, роутеры и middleware; сеть Telegram подменена."""
import time
from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteBusinessMessages,
    EditMessageText,
    GetMe,
    SendMessage,
)
from aiogram.types import Chat, Message, Update, User
from sqlalchemy import select

from app.bot.callbacks import Cb
from app.bot.handlers import build_routers
from app.bot.middlewares import DedupMiddleware
from app.business.service import BusinessService
from app.context import AppContext
from app.db.models import Conversation, Owner, TradeBotConfig
from app.deals.manager import DealManager
from app.media.analyzer import MediaAnalyzer
from app.trading.registry import AdapterFactory
from tests.conftest import ADMIN_ID, OWNER_TG, FakeLLM

BOT_USER = User(id=42, is_bot=True, first_name="Agent", username="agent_test_bot", can_connect_to_business=True)


class MockSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def close(self):
        pass

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(message_id=len(self.requests), date=datetime.now(timezone.utc),
                           chat=Chat(id=getattr(method, "chat_id", 1) or 1, type="private"), text=method.text)
        if isinstance(method, (AnswerCallbackQuery, DeleteBusinessMessages)):
            return True
        return True


@pytest.fixture
async def panel(sessions, settings):
    session = MockSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode="HTML"))
    llm = FakeLLM()
    factory = AdapterFactory(settings)
    ctx = AppContext(settings=settings, bot=bot, sessions=sessions, llm=llm, media=MediaAnalyzer(llm, None),
                     trade_adapters=factory, deals=DealManager(factory), gifts=None)
    ctx.business = BusinessService(ctx)
    dp = Dispatcher()
    dp.update.outer_middleware(DedupMiddleware(ctx))
    dp.include_routers(*build_routers(ctx))
    counter = iter(range(1, 10_000))

    async def feed(update_id=None, **payload):
        uid = update_id if update_id is not None else next(counter)
        await dp.feed_update(bot, Update.model_validate({"update_id": uid, **payload}, context={"bot": bot}))

    return feed, session, ctx


def message(text, user_id=OWNER_TG, **extra):
    return {"message_id": 1, "date": int(time.time()), "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "U"}, "text": text, **extra}


def callback(data, user_id=OWNER_TG):
    return {"id": "cq", "chat_instance": "x", "data": data, "from": {"id": user_id, "is_bot": False, "first_name": "U"},
            "message": message("panel", user_id)}


def texts(session):
    return [r.text for r in session.requests if isinstance(r, (SendMessage, EditMessageText))]


async def test_start_shows_menu_and_guide(panel, sessions):
    feed, session, _ = panel
    await feed(message=message("/start"))
    out = texts(session)
    assert any("Панель ИИ-агента" in t for t in out)
    assert any("Telegram для бизнеса" in t and "@agent_test_bot" in t for t in out)
    async with sessions() as s:
        assert await s.scalar(select(Owner).where(Owner.telegram_id == OWNER_TG))


async def test_stranger_has_no_access(panel):
    feed, session, _ = panel
    await feed(message=message("/start", user_id=5))
    assert texts(session) == ["⛔️ Доступ к панели не выдан. Обратитесь к администратору."]


@pytest.mark.parametrize("section", ["agent", "biz", "parsers", "tpl", "ai", "trade", "deals", "media", "stats", "log",
                                     "settings", "pause", "resume"])
async def test_every_section_opens(panel, section):
    feed, session, _ = panel
    await feed(message=message("/start"))
    await feed(callback_query=callback(Cb(s=section).pack()))
    assert not any("Traceback" in t for t in texts(session))
    assert any(isinstance(r, EditMessageText) for r in session.requests), section


async def test_admin_section_only_for_admin(panel):
    feed, session, _ = panel
    await feed(callback_query=callback(Cb(s="admin").pack()))
    answers = [r for r in session.requests if isinstance(r, AnswerCallbackQuery)]
    assert answers and answers[-1].text == "Только для администратора"
    await feed(callback_query=callback(Cb(s="admin").pack(), user_id=ADMIN_ID))
    assert any("глобальные инструкции" in t for t in texts(session))


async def test_template_input_flow(panel, sessions):
    feed, session, _ = panel
    await feed(callback_query=callback(Cb(s="tpl", a="add").pack()))
    await feed(message=message("Здравствуйте! Продаёте подарок?"))
    assert any("Шаблон сохранён" in t for t in texts(session))


async def test_trade_bot_is_added_only_via_shared_bot_id(panel, sessions):
    feed, session, ctx = panel
    ctx.settings.crypto_pay_api_token = "tok"
    await feed(callback_query=callback(Cb(s="trade", a="add_type", i=1).pack()))
    await feed(message=message(None, users_shared={"request_id": 1, "users": [{"user_id": 1559501630, "username": "CryptoBot"}]}))
    async with sessions() as s:
        cfg = await s.scalar(select(TradeBotConfig))
    assert cfg.bot_user_id == 1559501630 and cfg.bot_username == "cryptobot" and cfg.verified_at
    # Похожий бот отклоняется.
    await feed(callback_query=callback(Cb(s="trade", a="add_type", i=1).pack()))
    await feed(message=message(None, users_shared={"request_id": 1, "users": [{"user_id": 7, "username": "CryptoBotPay"}]}))
    assert any("официальный бот" in t for t in texts(session))


async def test_duplicate_update_processed_once(panel):
    feed, session, _ = panel
    await feed(update_id=5000, message=message("/start"))
    first = len(texts(session))
    await feed(update_id=5000, message=message("/start"))
    assert first > 0 and len(texts(session)) == first


async def test_business_takeover_through_dispatcher(panel, sessions):
    feed, session, ctx = panel
    await feed(business_connection={"id": "bc1", "user": {"id": OWNER_TG, "is_bot": False, "first_name": "O"},
                                    "user_chat_id": OWNER_TG, "date": int(time.time()), "is_enabled": True,
                                    "rights": {"can_reply": True, "can_read_messages": True, "can_delete_all_messages": True}})
    assert any("Бизнес-аккаунт подключён" in t for t in texts(session))
    base = {"date": int(time.time()), "business_connection_id": "bc1",
            "chat": {"id": 555, "type": "private", "first_name": "Seller"}}
    await feed(business_message={**base, "message_id": 10, "from": {"id": 555, "is_bot": False, "first_name": "S"}, "text": "Привет"})
    await feed(business_message={**base, "message_id": 11, "from": {"id": OWNER_TG, "is_bot": False, "first_name": "O"},
                                 "text": "сутпасмотри"})
    async with sessions() as s:
        conv = await s.scalar(select(Conversation))
    assert conv.mode == "manual"
    deletes = [r for r in session.requests if isinstance(r, DeleteBusinessMessages)]
    assert deletes and deletes[0].message_ids == [11]
