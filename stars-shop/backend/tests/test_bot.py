"""Bot handlers driven through the real aiogram dispatcher with a fake Bot API session."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy import select

from starshop.bot.main import build_dispatcher
from starshop.database.models import AdminLoginToken, Referral, SupportTicket
from tests.conftest import BOT_TOKEN, get_user, make_admin, set_runtime

CHAT = Chat(id=777, type="private")
USER = User(id=777, is_bot=False, first_name="Анна", username="anna_buyer")


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:  # noqa: ASYNC109 - aiogram signature
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(message_id=len(self.calls), date=datetime.now(UTC), chat=CHAT, text=method.text)
        if isinstance(method, AnswerCallbackQuery):
            return True
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:  # pragma: no cover
        yield b""

    def texts(self) -> list[str]:
        return [m.text for m in self.calls if isinstance(m, (SendMessage, EditMessageText))]

    def last_markup_texts(self) -> list[str]:
        for m in reversed(self.calls):
            if isinstance(m, (SendMessage, EditMessageText)) and m.reply_markup is not None:
                return [b.text for row in m.reply_markup.inline_keyboard for b in row]
        return []


_DISPATCHER = None


def dispatcher():
    # Routers are module singletons and can be attached only once.
    global _DISPATCHER
    if _DISPATCHER is None:
        _DISPATCHER = build_dispatcher()
    _DISPATCHER.fsm.storage = MemoryStorage()
    return _DISPATCHER


@pytest.fixture
def bot_env():
    session = FakeSession()
    bot = Bot(BOT_TOKEN, session=session)
    dp = dispatcher()
    counter = {"n": 0}

    async def send_text(text: str, user: User = USER) -> None:
        counter["n"] += 1
        msg = Message(message_id=counter["n"], date=datetime.now(UTC), chat=Chat(id=user.id, type="private"), from_user=user, text=text)
        await dp.feed_update(bot, Update(update_id=counter["n"], message=msg))

    async def press(data: str, user: User = USER) -> None:
        counter["n"] += 1
        msg = Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=user.id, type="private"), text="menu")
        cq = CallbackQuery(id=str(counter["n"]), from_user=user, chat_instance="ci", data=data, message=msg)
        await dp.feed_update(bot, Update(update_id=counter["n"], callback_query=cq))

    return session, send_text, press


async def test_start_shows_menu_and_registers_user(bot_env, session):
    calls, send, _ = bot_env
    await send("/start")
    text = calls.texts()[-1]
    assert "Анна" in text and "DEMO" in text
    buttons = calls.last_markup_texts()
    for label in (
        "✨ Открыть магазин",
        "✨ Купить Stars",
        "👤 Мой профиль",
        "🧾 Мои заказы",
        "💳 Способы оплаты",
        "🎁 Бонусы",
        "💬 Поддержка",
    ):
        assert label in buttons
    # Mini App buttons use web_app with the HTTPS shop URL
    sent = [m for m in calls.calls if isinstance(m, SendMessage)][-1]
    assert sent.reply_markup.inline_keyboard[0][0].web_app.url == "https://shop.test/"
    user = await get_user(session, 777)
    assert user.bot_started and user.username == "anna_buyer"


async def test_start_with_referral_code(bot_env, session):
    _, send, _ = bot_env
    await set_runtime(session, "referral", enabled=True)
    inviter = User(id=1001, is_bot=False, first_name="Inviter")
    await send("/start", user=inviter)
    code = (await get_user(session, 1001)).referral_code
    await send(f"/start ref_{code}")
    ref = (await session.execute(select(Referral))).scalar_one()
    assert ref.referrer_id == (await get_user(session, 1001)).id


async def test_profile_and_orders_screens(bot_env):
    calls, send, press = bot_env
    await send("/start")
    await press("menu:profile")
    assert "Telegram ID: <code>777</code>" in calls.texts()[-1]
    await press("menu:orders")
    assert "Заказов пока нет" in calls.texts()[-1]
    await press("menu:payments")
    assert "DEMO-оплата" in calls.texts()[-1]
    await press("menu:bonus")
    assert "не активна" in calls.texts()[-1]


async def test_support_flow_creates_ticket(bot_env, session):
    calls, send, press = bot_env
    await send("/start")
    await press("menu:support")
    await send("Не пришли звёзды по заказу")
    assert "обращение" in calls.texts()[-1]
    ticket = (await session.execute(select(SupportTicket))).scalar_one()
    assert ticket.subject.startswith("Не пришли звёзды")
    # Commands still work while the support prompt is open
    await press("menu:support")
    await send("/start")
    assert "Анна" in calls.texts()[-1]


async def test_admin_command(bot_env, session):
    calls, send, _ = bot_env
    await send("/admin")
    assert "Неизвестная команда" in calls.texts()[-1]
    await make_admin(session, telegram_id=777)
    await send("/admin")
    assert "Ссылка для входа" in calls.texts()[-1]
    assert "🔐 Войти в админ-панель" in calls.last_markup_texts()
    await session.commit()
    assert (await session.execute(select(AdminLoginToken))).scalar_one().used_at is None
