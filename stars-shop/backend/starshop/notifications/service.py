"""Transactional outbox for Telegram messages.

Messages are inserted in the same DB transaction as the state change they
describe, so a "Stars delivered" message can only exist if the delivery was
actually committed. The worker sends them afterwards (see ``sender.py``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import AdminRole
from ..database.models import AdminUser, Notification, Order, User
from ..services.app_settings import RuntimeSettings
from ..shared.demo_identity import is_demo_user_id
from . import templates
from .templates import Message


async def enqueue(
    session: AsyncSession,
    *,
    chat_id: int,
    kind: str,
    message: Message,
    dedup_key: str,
    user_id: int | None = None,
    order_id: uuid.UUID | None = None,
) -> None:
    if is_demo_user_id(chat_id):  # a visitor of the public DEMO site has no Telegram chat
        return
    stmt = (
        insert(Notification)
        .values(
            chat_id=chat_id,
            user_id=user_id,
            order_id=order_id,
            kind=kind,
            text=message.text,
            reply_markup=message.reply_markup,
            dedup_key=dedup_key[:128],
        )
        .on_conflict_do_nothing(index_elements=[Notification.dedup_key])
    )
    await session.execute(stmt)


async def notify_order(
    session: AsyncSession,
    order: Order,
    kind: str,
    message: Message,
    runtime: RuntimeSettings,
    *,
    dedup_suffix: str = "",
) -> None:
    if not runtime.notifications.user_notifications:
        return
    user = await session.get(User, order.user_id)
    if user is None:
        return
    await enqueue(
        session,
        chat_id=user.telegram_id,
        kind=kind,
        message=message,
        dedup_key=f"{kind}:{order.id}{dedup_suffix}",
        user_id=user.id,
        order_id=order.id,
    )


async def notify_admins(
    session: AsyncSession,
    kind: str,
    message: Message,
    dedup_key: str,
    *,
    roles: tuple[AdminRole, ...] = (AdminRole.owner, AdminRole.manager),
) -> None:
    admins = (await session.execute(select(AdminUser).where(AdminUser.is_active.is_(True), AdminUser.role.in_(roles)))).scalars()
    for admin in admins:
        await enqueue(
            session,
            chat_id=admin.telegram_id,
            kind=kind,
            message=message,
            dedup_key=f"admin:{admin.id}:{dedup_key}",
        )


async def admin_attention(session: AsyncSession, order: Order, reason: str, runtime: RuntimeSettings, key: str) -> None:
    if runtime.notifications.admin_delivery_problem:
        await notify_admins(session, "admin_attention", templates.admin_attention(order, reason), f"attention:{order.id}:{key}")
