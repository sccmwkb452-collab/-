"""Dialogue state of the bot (aiogram FSM) in PostgreSQL.

Every user's purchase or support dialogue lives in its own row, keyed by
bot, chat and user, so instances of the bot (or serverless invocations) see
the same state. Redis is used instead when REDIS_URL is set.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..database.models import BotState
from ..database.session import session_scope
from ..shared.timeutil import utcnow


def _key(key: StorageKey) -> str:
    return ":".join(
        str(part) for part in (key.bot_id, key.chat_id, key.user_id, key.thread_id or "", key.business_connection_id or "", key.destiny)
    )


def _state_name(state: StateType) -> str | None:
    return state.state if isinstance(state, State) else state


class DbStorage(BaseStorage):
    async def _upsert(self, key: StorageKey, **values: Any) -> None:
        async with session_scope() as session:
            stmt = insert(BotState).values(key=_key(key), updated_at=utcnow(), **values)
            await session.execute(stmt.on_conflict_do_update(index_elements=[BotState.key], set_={**values, "updated_at": utcnow()}))

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        await self._upsert(key, state=_state_name(state))

    async def get_state(self, key: StorageKey) -> str | None:
        async with session_scope() as session:
            return await session.scalar(select(BotState.state).where(BotState.key == _key(key)))

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._upsert(key, data=dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with session_scope() as session:
            data = await session.scalar(select(BotState.data).where(BotState.key == _key(key)))
        return dict(data or {})

    async def close(self) -> None:
        pass
