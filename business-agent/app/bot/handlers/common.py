from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def show(cq: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Обновляет сообщение панели; если нельзя (медиа/устарело) — отправляет новое."""
    try:
        await cq.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" not in exc.message:
            await cq.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
    await cq.answer()
