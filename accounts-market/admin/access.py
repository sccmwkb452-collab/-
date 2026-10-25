from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject


class IsAdmin(Filter):
    """Server-side check of the sender against ADMIN_IDS for every admin update."""

    def __init__(self, admin_ids: frozenset[int]) -> None:
        self.admin_ids = admin_ids

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in self.admin_ids


def is_admin(event: Message | CallbackQuery, admin_ids: frozenset[int]) -> bool:
    return event.from_user is not None and event.from_user.id in admin_ids
