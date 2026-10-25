"""In-process imitation of the Telegram Bot API for the beta site.

The beta site's Bot object talks to this session instead of api.telegram.org:
nothing it does ever reaches real Telegram users.
"""

from __future__ import annotations

import itertools
import secrets
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    DeleteMessage,
    EditMessageMedia,
    EditMessageText,
    GetMe,
    SendMessage,
    SendPhoto,
    SetMyCommands,
    TelegramMethod,
)
from aiogram.types import BufferedInputFile, Chat, Message, MessageId, PhotoSize, User

BOT_USER = User(id=1, is_bot=True, first_name="Beta", username="beta_preview_bot")
MAX_MESSAGES = 80
MAX_MEDIA = 300


class BetaTelegram(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.chats: dict[int, list[Message]] = {}
        self.media: OrderedDict[str, bytes] = OrderedDict()
        self.toasts: dict[int, list[tuple[str, bool]]] = {}
        self._ids = itertools.count(1)

    async def close(self) -> None:
        return None

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - downloads are not supported
        raise NotImplementedError
        yield b""

    # ── helpers ──────────────────────────────────────────────────────────────

    def next_id(self) -> int:
        return next(self._ids)

    def _photo(self, file: Any) -> list[PhotoSize]:
        if isinstance(file, BufferedInputFile):
            file_id = "b" + secrets.token_hex(8)
            self.media[file_id] = file.data
            while len(self.media) > MAX_MEDIA:
                self.media.popitem(last=False)
        else:
            file_id = str(file)  # cached file_id from an earlier upload (or a real Telegram id)
        return [PhotoSize(file_id=file_id, file_unique_id=file_id, width=1280, height=640)]

    def message(self, chat_id: int, *, sender: User = BOT_USER, message_id: int | None = None, **fields) -> Message:
        return Message(
            message_id=message_id or self.next_id(),
            date=datetime.now(timezone.utc),
            chat=Chat(id=chat_id, type="private"),
            from_user=sender,
            **fields,
        )

    def put(self, msg: Message) -> Message:
        chat = self.chats.setdefault(msg.chat.id, [])
        for i, old in enumerate(chat):
            if old.message_id == msg.message_id:
                chat[i] = msg  # edits stay in place
                return msg
        chat.append(msg)
        del chat[:-MAX_MESSAGES]
        return msg

    def find(self, chat_id: int, message_id: int) -> Message | None:
        return next((m for m in self.chats.get(chat_id, []) if m.message_id == message_id), None)

    # ── Bot API ──────────────────────────────────────────────────────────────

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, SendMessage):
            return self.put(self.message(method.chat_id, text=method.text, reply_markup=method.reply_markup))
        if isinstance(method, SendPhoto):
            return self.put(
                self.message(method.chat_id, caption=method.caption, photo=self._photo(method.photo), reply_markup=method.reply_markup)
            )
        if isinstance(method, EditMessageMedia):
            old = self.find(method.chat_id, method.message_id)
            if old is None or not old.photo:
                return self._bad("message to edit not found")
            return self.put(
                self.message(
                    method.chat_id,
                    message_id=old.message_id,
                    caption=method.media.caption,
                    photo=self._photo(method.media.media),
                    reply_markup=method.reply_markup,
                )
            )
        if isinstance(method, EditMessageText):
            old = self.find(method.chat_id, method.message_id)
            if old is None or old.text is None:
                return self._bad("message to edit not found")
            if old.text == method.text and old.reply_markup == method.reply_markup:
                return self._bad("message is not modified")
            return self.put(self.message(method.chat_id, message_id=old.message_id, text=method.text, reply_markup=method.reply_markup))
        if isinstance(method, DeleteMessage):
            self.chats[method.chat_id] = [m for m in self.chats.get(method.chat_id, []) if m.message_id != method.message_id]
            return True
        if isinstance(method, CopyMessage):
            source = self.find(method.from_chat_id, method.message_id)
            fields = {"text": "📢 Рассылка"} if source is None else {
                "text": source.html_text if source.text else None,
                "caption": source.caption,
                "photo": source.photo,
            }
            msg = self.put(self.message(method.chat_id, **{k: v for k, v in fields.items() if v is not None} or {"text": "📢"}))
            return MessageId(message_id=msg.message_id)
        if isinstance(method, AnswerCallbackQuery):
            if method.text:
                self.toasts.setdefault(int(method.callback_query_id.split(":")[0]), []).append((method.text, bool(method.show_alert)))
            return True
        if isinstance(method, SetMyCommands):
            return True
        return self._bad(f"{type(method).__name__} is not available in the beta")

    @staticmethod
    def _bad(message: str):
        from aiogram.exceptions import TelegramBadRequest

        raise TelegramBadRequest(method=None, message=message)  # type: ignore[arg-type]
