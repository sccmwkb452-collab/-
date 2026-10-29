"""Обновления Telegram Business → BusinessService."""
from aiogram import Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message


def setup(ctx) -> Router:
    router = Router(name="business")

    @router.business_connection()
    async def on_connection(bc: BusinessConnection) -> None:
        await ctx.business.on_connection(bc)

    @router.business_message()
    async def on_message(message: Message) -> None:
        await ctx.business.on_message(message)

    @router.edited_business_message()
    async def on_edited(message: Message) -> None:
        await ctx.business.on_edited(message)

    @router.deleted_business_messages()
    async def on_deleted(event: BusinessMessagesDeleted) -> None:
        await ctx.business.on_deleted(event.business_connection_id, event.chat.id, list(event.message_ids))

    return router
