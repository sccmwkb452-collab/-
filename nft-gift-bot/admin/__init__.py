"""
Админ-панель бота.

Доступна только пользователям из BOT_ADMIN_IDS.
Команды:
  /admin           — главное меню администратора
  /admin users     — статистика пользователей
  /admin subs      — управление подписками
  /admin broadcast — рассылка сообщений
"""

from admin.router import admin_router
from admin.shop_admin import shop_admin_router

__all__ = ["admin_router", "shop_admin_router"]
