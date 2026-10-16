import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import AdminFilter
from services.user_service import UserService

logger = logging.getLogger(__name__)

admin_router = Router(name="admin")
admin_router.message.filter(AdminFilter())


@admin_router.message(Command("admin"))
async def cmd_admin_panel(message: Message, session: AsyncSession) -> None:
    user_service = UserService(session)
    total = await user_service.get_total_users()

    await message.answer(
        "🛠 <b>Панель администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{total}</b>\n\n"
        "<b>Команды:</b>\n"
        "/admin — эта страница\n"
        "<i>Остальные команды будут добавлены в следующих версиях.</i>",
        parse_mode="HTML",
    )
