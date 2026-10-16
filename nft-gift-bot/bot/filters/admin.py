from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import settings
from database.models.user import User


class AdminFilter(BaseFilter):
    """
    Allows only admin users — checked against both:
    - settings.bot_admin_ids (env-defined super-admins), and
    - db_user.is_admin (DB-managed admins, injected by UserMiddleware).
    """

    async def __call__(
        self,
        event: Message | CallbackQuery,
        db_user: User | None = None,
    ) -> bool:
        from_user = event.from_user
        if not from_user:
            return False

        if from_user.id in settings.bot_admin_ids:
            return True

        if db_user is not None and db_user.is_admin:
            return True

        return False
