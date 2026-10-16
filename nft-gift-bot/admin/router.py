import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import AdminFilter
from database.repositories.audit_repo import AuditRepository
from payments.payment_service import PaymentService
from services.shop_service import ShopService

logger = logging.getLogger(__name__)

admin_router = Router(name="admin")
admin_router.message.filter(AdminFilter())


@admin_router.message(Command("set"))
async def cmd_set(message: Message, command: CommandObject, session: AsyncSession) -> None:
    """Usage: /set sub_duration_days 30 | /set sub_price_ton 10 | /set shop_price_ton 5"""
    args = (command.args or "").split()
    if len(args) != 2:
        await message.answer(
            "Использование:\n"
            "  /set sub_duration_days &lt;N&gt;\n"
            "  /set sub_price_ton &lt;N&gt;\n"
            "  /set shop_price_ton &lt;N&gt;",
            parse_mode="HTML",
        )
        return

    key, raw_value = args[0], args[1]
    admin_id = message.from_user.id
    audit = AuditRepository(session)

    if key == "sub_duration_days":
        if not raw_value.isdigit() or int(raw_value) < 1:
            await message.answer("Значение должно быть целым числом > 0")
            return
        await PaymentService(session).set_sub_duration(int(raw_value))
        await audit.log(admin_id, "set_setting", f"sub_duration_days={raw_value}")
        await session.commit()
        await message.answer(f"✅ sub_duration_days = {raw_value}")
        logger.info("Admin %d set sub_duration_days=%s", admin_id, raw_value)

    elif key == "sub_price_ton":
        try:
            price = float(raw_value)
            if price <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Значение должно быть числом > 0")
            return
        await PaymentService(session).set_sub_price(price)
        await audit.log(admin_id, "set_setting", f"sub_price_ton={price}")
        await session.commit()
        await message.answer(f"✅ sub_price_ton = {price}")
        logger.info("Admin %d set sub_price_ton=%s", admin_id, raw_value)

    elif key == "shop_price_ton":
        try:
            price = float(raw_value)
            if price <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Значение должно быть числом > 0")
            return
        await ShopService(session).set_default_price(price)
        await audit.log(admin_id, "set_setting", f"shop_price_ton={price}")
        await session.commit()
        await message.answer(f"✅ shop_price_ton = {price}")
        logger.info("Admin %d set shop_price_ton=%s", admin_id, raw_value)

    else:
        await message.answer(f"Неизвестный ключ: {key}")
