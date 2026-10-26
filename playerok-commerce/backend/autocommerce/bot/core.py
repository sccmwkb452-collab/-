"""Bot infrastructure: access control, database session per update, screen
rendering (edit in place), free-text input dispatch and error handling."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject

from ..database.session import get_sessionmaker
from ..services import auth
from ..services.audit import Actor
from ..shared.errors import DomainError
from .ui import b, kb

log = logging.getLogger("autocommerce.bot")

InputHandler = Callable[[Message, dict[str, Any]], Awaitable[None]]
INPUTS: dict[str, InputHandler] = {}


class Input(StatesGroup):
    waiting = State()


def on_input(kind: str) -> Callable[[InputHandler], InputHandler]:
    def register(func: InputHandler) -> InputHandler:
        INPUTS[kind] = func
        return func

    return register


async def ask(event: CallbackQuery | Message, state: FSMContext, kind: str, prompt: str, *, back: str = "home", **data: Any) -> None:
    """Switch to free-text input. The next text message goes to INPUTS[kind]."""
    await state.set_state(Input.waiting)
    await state.update_data(kind=kind, back=back, **data)
    await show(event, f"✍️ {prompt}\n\n<i>Отправьте ответ сообщением. «Отмена» — кнопкой ниже.</i>", kb([b("✖️ Отмена", f"cancel:{back}")]))


class AccessMiddleware(BaseMiddleware):
    """Opens one transaction per update and resolves who is writing.
    Users without access get their Telegram ID and nothing else."""

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return None
        async with get_sessionmaker()() as session:
            try:
                actor = await auth.telegram_actor(session, user.id, user.full_name or user.username)
                data["session"] = session
                data["actor"] = actor
                if actor is None:
                    text = getattr(event, "text", "") or ""
                    if isinstance(event, Message) and text.startswith("/start link_"):
                        result = await handler(event, data)
                        await session.commit()
                        return result
                    await _deny(event, user.id)
                    await session.commit()
                    return None
                result = await handler(event, data)
                await session.commit()
                return result
            except DomainError as exc:
                await session.rollback()
                await _error(event, exc.message)
            except Exception:
                await session.rollback()
                log.exception("bot handler failed")
                await _error(event, "Внутренняя ошибка. Действие не выполнено, подробности в логах.")
        return None


async def _deny(event: TelegramObject, telegram_id: int) -> None:
    text = (
        "🔒 <b>Нет доступа</b>\n\n"
        f"Ваш Telegram ID: <code>{telegram_id}</code>\n"
        "Это приватный бот управления магазином. Владелец может добавить ID в OWNER_TELEGRAM_IDS "
        "или выдать код привязки в веб-панели (Пользователи → Привязать Telegram)."
    )
    if isinstance(event, CallbackQuery):
        await event.answer("Нет доступа", show_alert=True)
    elif isinstance(event, Message):
        await event.answer(text)


async def _error(event: TelegramObject, message: str) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.answer(message[:190], show_alert=True)
        except TelegramBadRequest:
            pass
    elif isinstance(event, Message):
        await event.answer(f"⚠️ {message}")


async def show(event: CallbackQuery | Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit the screen in place for button presses, send a new message otherwise."""
    if isinstance(event, CallbackQuery):
        message = event.message
        if isinstance(message, Message):
            if not (message.photo or message.document):
                try:
                    await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
                    await event.answer()
                    return
                except TelegramBadRequest as exc:
                    if "message is not modified" in str(exc):
                        await event.answer()
                        return
            await message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        await event.answer()
        return
    await event.answer(text, reply_markup=markup, disable_web_page_preview=True)


def require(actor: Actor, permission: str) -> None:
    auth.require(actor, permission)


def make_router(name: str) -> Router:
    return Router(name=name)
