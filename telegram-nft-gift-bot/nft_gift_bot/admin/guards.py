"""Admin access is decided only by the numeric Telegram user ID from ADMIN_IDS.

Usernames, display names or anything the user types are never considered.
"""

from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message


def is_admin(telegram_id: int | None, admin_ids: frozenset[int]) -> bool:
    return telegram_id is not None and telegram_id in admin_ids


class AdminFilter(Filter):
    def __init__(self, admin_ids: frozenset[int]) -> None:
        self._admin_ids = admin_ids

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return is_admin(user.id if user else None, self._admin_ids)
