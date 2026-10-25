"""Broadcasts: copies an admin's message to every user, respecting Telegram limits."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import Broadcast, BroadcastStatus, User

log = logging.getLogger(__name__)

RATE = 20  # messages per second, below Telegram's ~30/s limit


async def recipients_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count(User.id)).where(User.is_banned.is_(False), User.bot_blocked.is_(False))
        )
        or 0
    )


async def run(bot: Bot, sm: async_sessionmaker[AsyncSession], broadcast_id: int) -> Broadcast:
    async with sm() as session:
        bc = await session.get(Broadcast, broadcast_id)
        ids = list(
            (
                await session.execute(
                    select(User.id)
                    .where(User.is_banned.is_(False), User.bot_blocked.is_(False))
                    .order_by(User.id)
                )
            ).scalars()
        )
    sent = failed = blocked = 0
    blocked_ids: list[int] = []
    for index, user_id in enumerate(ids, start=1):
        for attempt in range(3):
            try:
                await bot.copy_message(user_id, bc.source_chat_id, bc.source_message_id)
                sent += 1
                break
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError:
                blocked += 1
                blocked_ids.append(user_id)
                break
            except TelegramBadRequest as exc:
                log.info("broadcast %s: user %s bad request: %s", broadcast_id, user_id, exc.message)
                failed += 1
                break
        else:
            failed += 1
        if index % RATE == 0:
            await asyncio.sleep(1)
        if index % 200 == 0:
            await _save(sm, broadcast_id, sent, failed, blocked, final=False)
    async with sm() as session, session.begin():
        if blocked_ids:
            await session.execute(update(User).where(User.id.in_(blocked_ids)).values(bot_blocked=True))
    return await _save(sm, broadcast_id, sent, failed, blocked, final=True)


async def _save(sm, broadcast_id: int, sent: int, failed: int, blocked: int, *, final: bool) -> Broadcast:
    async with sm() as session, session.begin():
        bc = await session.get(Broadcast, broadcast_id)
        bc.sent, bc.failed, bc.blocked = sent, failed, blocked
        if final:
            bc.status = BroadcastStatus.DONE
            bc.finished_at = func.now()
        await session.flush()
        await session.refresh(bc)
        return bc
