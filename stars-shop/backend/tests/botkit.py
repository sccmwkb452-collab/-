"""Bot test kit: the real aiogram dispatcher with a fake Bot API session."""

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

from starshop.bot.main import get_dispatcher
from tests.conftest import BOT_TOKEN

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


def dispatcher():
    dp = get_dispatcher()
    dp.fsm.storage = MemoryStorage()
    return dp


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
