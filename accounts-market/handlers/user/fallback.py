"""Catches anything no other handler took: stale buttons and random text."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer

from keyboards import user as kb

router = Router(name="fallback")


@router.callback_query()
async def stale_callback(callback: CallbackQuery, callback_answer: CallbackAnswer) -> None:
    callback_answer.text = "Кнопка устарела. Откройте меню заново: /start"
    callback_answer.show_alert = True


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer("Я понимаю кнопки меню 🙂 Нажмите, чтобы открыть магазин:", reply_markup=kb.only_home())
