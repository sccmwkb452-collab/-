import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import AdminFilter
from payments.payment_service import PaymentService
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
        "/set sub_duration_days &lt;N&gt; — срок подписки в днях\n",
        parse_mode="HTML",
    )


@admin_router.message(Command("set"))
async def cmd_set(message: Message, command: CommandObject, session: AsyncSession) -> None:
    """Usage: /set sub_duration_days 30"""
    args = (command.args or "").split()
    if len(args) != 2:
        await message.answer("Использование: /set sub_duration_days &lt;N&gt;", parse_mode="HTML")
        return

    key, raw_value = args[0], args[1]

    if key == "sub_duration_days":
        if not raw_value.isdigit() or int(raw_value) < 1:
            await message.answer("Значение должно быть целым числом > 0")
            return
        await PaymentService(session).set_sub_duration(int(raw_value))
        await session.commit()
        await message.answer(f"✅ sub_duration_days = {raw_value}")
        logger.info("Admin %d set sub_duration_days=%s", message.from_user.id, raw_value)
    else:
        await message.answer(f"Неизвестный ключ: {key}")
