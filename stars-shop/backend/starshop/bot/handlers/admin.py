from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...services.admin_auth import admin_by_telegram_id, ensure_bootstrap_admins, issue_login_token

router = Router(name="admin")


@router.message(Command("admin"))
async def admin_login(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.chat.type != "private":
        return
    await ensure_bootstrap_admins(session)
    await session.flush()
    admin = await admin_by_telegram_id(session, message.from_user.id)
    if admin is None:
        # Do not reveal that the command exists.
        await message.answer("Неизвестная команда. Нажмите /start, чтобы открыть меню.")
        return
    token = await issue_login_token(session, admin)
    s = get_settings()
    url = f"{s.admin_url}login#token={token}"
    rows = []
    if url.startswith("https://"):
        rows.append([InlineKeyboardButton(text="🔐 Войти в админ-панель", url=url)])
        rows.append([InlineKeyboardButton(text="📱 Открыть в Telegram", web_app=WebAppInfo(url=s.admin_url))])
    text = f"🔐 Ссылка для входа действует {s.admin_login_token_minutes} мин и работает один раз.\nНикому её не пересылайте."
    if not rows:
        text += f"\n\n<code>{url}</code>"
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None)
