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

__all__ = ["admin_router"]
