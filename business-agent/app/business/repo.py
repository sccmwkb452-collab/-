from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.state import DealState
from app.db.models import (
    BusinessConnectionRecord,
    Contact,
    Conversation,
    ConversationMessage,
    InitialTemplate,
    Owner,
    utcnow,
)


async def get_or_create_contact(
    session: AsyncSession, owner_id: int, telegram_user_id: int, username: str | None, name: str | None
) -> Contact:
    contact = await session.scalar(
        select(Contact).where(Contact.owner_id == owner_id, Contact.telegram_user_id == telegram_user_id)
    )
    uname = username.lower() if username else None
    if contact is None and uname:
        # Контакт мог прийти из парсера только с username — связываем с реальным ID.
        contact = await session.scalar(select(Contact).where(Contact.owner_id == owner_id, Contact.username == uname))
        if contact is not None:
            contact.telegram_user_id = telegram_user_id
    if contact is None:
        contact = Contact(owner_id=owner_id, telegram_user_id=telegram_user_id, username=uname, display_name=name,
                          source="incoming", profile={})
        session.add(contact)
        await session.flush()
    else:
        contact.display_name = name or contact.display_name
        if uname and contact.username != uname:
            clash = await session.scalar(select(Contact.id).where(Contact.owner_id == owner_id, Contact.username == uname))
            if clash is None:
                contact.username = uname
    return contact


async def get_or_create_conversation(
    session: AsyncSession, owner: Owner, rec: BusinessConnectionRecord, chat_id: int, contact: Contact
) -> tuple[Conversation, bool]:
    conv = await session.scalar(
        select(Conversation).where(Conversation.business_connection_id == rec.id, Conversation.chat_id == chat_id)
    )
    if conv is not None:
        return conv, False
    conv = Conversation(owner_id=owner.id, contact_id=contact.id, business_connection_id=rec.id, chat_id=chat_id,
                        state=DealState().dump(), mode="auto")
    session.add(conv)
    await session.flush()
    await session.refresh(conv, ["contact"])
    return conv, True


async def add_message(
    session: AsyncSession, owner: Owner, conv: Conversation, sender: str, text: str,
    telegram_message_id: int | None = None, media: dict[str, Any] | None = None,
) -> ConversationMessage | None:
    """Сохраняет сообщение. Объём хранимой истории ограничивает trim_history()."""
    msg = ConversationMessage(
        conversation_id=conv.id, telegram_message_id=telegram_message_id, sender=sender, text=text or "", media=media,
        created_at=utcnow(),
    )
    session.add(msg)
    await session.flush()
    return msg


async def recent_messages(session: AsyncSession, conv_id: int, limit: int = 40) -> list[ConversationMessage]:
    rows = (await session.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conv_id, ConversationMessage.deleted.is_(False))
        .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        .limit(limit)
    )).all()
    return list(reversed(rows))


async def primary_template(session: AsyncSession, owner_id: int) -> InitialTemplate | None:
    return await session.scalar(
        select(InitialTemplate)
        .where(InitialTemplate.owner_id == owner_id, InitialTemplate.is_enabled.is_(True))
        .order_by(InitialTemplate.is_primary.desc(), InitialTemplate.id)
    )


async def owner_connection(session: AsyncSession, owner_id: int) -> BusinessConnectionRecord | None:
    rows = (await session.scalars(
        select(BusinessConnectionRecord).where(
            BusinessConnectionRecord.owner_id == owner_id, BusinessConnectionRecord.is_enabled.is_(True)
        ).order_by(BusinessConnectionRecord.updated_at.desc())
    )).all()
    for rec in rows:
        if rec.right("can_reply"):
            return rec
    return rows[0] if rows else None


PRIVATE_WINDOW = 12


async def trim_history(session: AsyncSession, owner: Owner, conv_id: int) -> None:
    """При выключенном хранении истории оставляет только короткое окно для контекста ответа."""
    if owner.store_history:
        return
    from sqlalchemy import delete

    keep = select(ConversationMessage.id).where(ConversationMessage.conversation_id == conv_id).order_by(
        ConversationMessage.created_at.desc(), ConversationMessage.id.desc()).limit(PRIVATE_WINDOW)
    keep_ids = list((await session.scalars(keep)).all())
    await session.execute(delete(ConversationMessage).where(
        ConversationMessage.conversation_id == conv_id, ConversationMessage.id.notin_(keep_ids)))
