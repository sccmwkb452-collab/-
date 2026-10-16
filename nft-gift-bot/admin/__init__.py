"""
Админ-панель бота.

Доступна только пользователям из BOT_ADMIN_IDS или с is_admin=True в БД.
  /admin        — инлайн-панель администратора
  /set <key> <value> — изменить настройку
"""

from admin.broadcast import broadcast_router
from admin.panel import panel_router
from admin.router import admin_router
from admin.shop_admin import shop_admin_router

__all__ = ["admin_router", "shop_admin_router", "panel_router", "broadcast_router"]
