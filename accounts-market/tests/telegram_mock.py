"""A fake Telegram Bot API: records every request and replies like Telegram would.

Lets tests press real inline buttons and walk through the bot end to end.
"""

from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    DeleteMessage,
    EditMessageMedia,
    EditMessageText,
    GetMe,
    SendDocument,
    SendMessage,
    SendPhoto,
    SetMyCommands,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    Document,
    InlineKeyboardMarkup,
    Message,
    MessageId,
    PhotoSize,
    Update,
    User,
)

BOT_USER = User(id=42, is_bot=True, first_name="Shop", username="test_shop_bot")


class FakeTelegram(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self.chats: dict[int, list[Message]] = {}  # visible messages per chat
        self._ids = itertools.count(1000)
        self.answers: list[AnswerCallbackQuery] = []
        self.documents: list[bytes] = []

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError
        yield b""

    def _message(self, chat_id: int, *, text=None, caption=None, photo=False, markup=None, message_id=None) -> Message:
        return Message(
            message_id=message_id or next(self._ids),
            date=datetime.now(timezone.utc),
            chat=Chat(id=chat_id, type="private"),
            from_user=BOT_USER,
            text=text,
            caption=caption,
            photo=[PhotoSize(file_id=f"photo{next(self._ids)}", file_unique_id="u", width=1280, height=640)] if photo else None,
            reply_markup=markup,
        )

    def _store(self, msg: Message) -> Message:
        chat = self.chats.setdefault(msg.chat.id, [])
        chat[:] = [m for m in chat if m.message_id != msg.message_id] + [msg]
        return msg

    def _find(self, chat_id: int, message_id: int) -> Message | None:
        return next((m for m in self.chats.get(chat_id, []) if m.message_id == message_id), None)

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        self.requests.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, SendMessage):
            assert len(method.text) <= 4096, "message too long"
            return self._store(self._message(method.chat_id, text=method.text, markup=method.reply_markup))
        if isinstance(method, SendPhoto):
            assert method.caption is None or len(method.caption) <= 1024, "caption too long"
            return self._store(self._message(method.chat_id, caption=method.caption, photo=True, markup=method.reply_markup))
        if isinstance(method, SendDocument):
            self.documents.append(method.document.data)
            msg = self._message(method.chat_id, caption=method.caption, markup=method.reply_markup)
            msg = msg.model_copy(update={"document": Document(file_id="doc", file_unique_id="doc", file_name=method.document.filename)})
            return self._store(msg)
        if isinstance(method, EditMessageMedia):
            old = self._find(method.chat_id, method.message_id)
            assert old is not None and old.photo, "edit_media of a non-photo message"
            caption = method.media.caption
            assert caption is None or len(caption) <= 1024, "caption too long"
            return self._store(self._message(method.chat_id, caption=caption, photo=True, markup=method.reply_markup, message_id=old.message_id))
        if isinstance(method, EditMessageText):
            old = self._find(method.chat_id, method.message_id)
            assert old is not None and old.text is not None, "edit_text of a non-text message"
            return self._store(self._message(method.chat_id, text=method.text, markup=method.reply_markup, message_id=old.message_id))
        if isinstance(method, DeleteMessage):
            self.chats[method.chat_id] = [m for m in self.chats.get(method.chat_id, []) if m.message_id != method.message_id]
            return True
        if isinstance(method, CopyMessage):
            msg = self._store(self._message(method.chat_id, text="(copy)"))
            return MessageId(message_id=msg.message_id)
        if isinstance(method, AnswerCallbackQuery):
            self.answers.append(method)
            return True
        if isinstance(method, SetMyCommands):
            return True
        raise AssertionError(f"unexpected method {type(method).__name__}")


class Client:
    """One Telegram user talking to the bot."""

    _update_ids = itertools.count(1)

    def __init__(self, dp, bot: Bot, tg: FakeTelegram, user_id: int, username: str = "buyer") -> None:
        self.dp, self.bot, self.tg = dp, bot, tg
        self.user = User(id=user_id, is_bot=False, first_name="Test", username=username)

    @property
    def last(self) -> Message:
        return self.tg.chats[self.user.id][-1]

    @property
    def screen(self) -> str:
        m = self.last
        return (m.caption or m.text or "").replace("\xa0", " ")

    def buttons(self, message: Message | None = None) -> list[str]:
        markup: InlineKeyboardMarkup | None = (message or self.last).reply_markup
        return [b.text.replace("\xa0", " ") for row in (markup.inline_keyboard if markup else []) for b in row]

    async def send(self, text: str) -> None:
        msg = Message(
            message_id=next(self.tg._ids),
            date=datetime.now(timezone.utc),
            chat=Chat(id=self.user.id, type="private"),
            from_user=self.user,
            text=text,
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), message=msg))

    async def click(self, label: str, message: Message | None = None) -> None:
        message = message or self.last
        markup = message.reply_markup
        assert markup is not None, f"no keyboard on: {self.screen[:80]}"
        for row in markup.inline_keyboard:
            for b in row:
                if label in b.text.replace("\xa0", " "):
                    assert b.callback_data, f"button {b.text!r} is not a callback button"
                    await self.press(b.callback_data, message)
                    return
        raise AssertionError(f"button {label!r} not found in {self.buttons(message)}")

    async def press(self, data: str, message: Message | None = None) -> None:
        cq = CallbackQuery(
            id=str(next(self._update_ids)),
            from_user=self.user,
            chat_instance="ci",
            data=data,
            message=message or self.last,
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), callback_query=cq))

    def last_answer(self) -> AnswerCallbackQuery | None:
        return self.tg.answers[-1] if self.tg.answers else None


def make_bot(tg: FakeTelegram) -> Bot:
    from aiogram.enums import ParseMode

    return Bot("42:TEST", session=tg, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
