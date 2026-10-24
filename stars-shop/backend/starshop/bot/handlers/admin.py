from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, StateFilter
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
        await message.answer(
            "🔐 Админ-панель доступна только администраторам магазина.\n\n"
            f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
            "Если вы владелец, добавьте этот ID в переменную <code>ADMIN_TELEGRAM_IDS</code> на сервере и снова отправьте /admin."
        )
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


@router.message(
    StateFilter(None), F.chat.type == "private", F.entities.func(lambda entities: any(e.type == "custom_emoji" for e in entities))
)
@router.message(StateFilter(None), F.chat.type == "private", F.sticker.custom_emoji_id)
async def custom_emoji_ids(message: Message, session: AsyncSession) -> None:
    """Administrators send premium emoji to learn their IDs for Admin → Настройки → Эмодзи бота."""
    if message.from_user is None or await admin_by_telegram_id(session, message.from_user.id) is None:
        raise SkipHandler
    ids: list[str] = []
    if message.sticker and message.sticker.custom_emoji_id:
        ids.append(message.sticker.custom_emoji_id)
    for entity in message.entities or []:
        if entity.type == "custom_emoji" and entity.custom_emoji_id and entity.custom_emoji_id not in ids:
            ids.append(entity.custom_emoji_id)
    lines = "\n".join(f"<code>{i}</code>" for i in ids)
    await message.answer(f"🧩 ID премиум-эмодзи:\n{lines}\n\nВставьте их в админке: Настройки → Эмодзи бота.")
