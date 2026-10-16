from __future__ import annotations

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from nft_gift_bot.bot.ui import Rich

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | None


async def respond(event: Message | CallbackQuery, rich: Rich, markup: Markup = None, edit: bool = False) -> None:
    """Answer a message or a callback in one consistent way."""
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message is None:
            return
        if edit and isinstance(event.message, Message) and isinstance(markup, (InlineKeyboardMarkup, type(None))):
            await event.message.edit_text(reply_markup=markup, **rich.kwargs())
            return
        await event.message.answer(reply_markup=markup, **rich.kwargs())
        return
    await event.answer(reply_markup=markup, **rich.kwargs())
