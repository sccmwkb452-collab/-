from __future__ import annotations

from aiogram import Router
from aiogram.types import Message

from admin.access import IsAdmin


def _not_foreign_command(message: Message) -> bool:
    text = message.text or ""
    return not text.startswith("/") or text.startswith("/admin")


def build_router(admin_ids: frozenset[int]) -> Router:
    from handlers.admin import broadcast, categories, orders, panel, payments, products, settings, users
    from handlers.user import catalog, fallback, menu, profile, purchase, referrals, topup

    root = Router(name="root")

    admin = Router(name="admin")
    admin.message.filter(IsAdmin(admin_ids))
    # Commands are never swallowed as input of an admin form (except /admin itself).
    admin.message.filter(_not_foreign_command)
    admin.callback_query.filter(IsAdmin(admin_ids))
    for module in (panel, products, categories, orders, users, payments, broadcast, settings):
        admin.include_router(module.router)

    # Admin first: its FSM inputs must win over the user fallback.
    root.include_router(admin)
    for module in (menu, catalog, purchase, profile, topup, referrals):
        root.include_router(module.router)
    root.include_router(fallback.router)
    return root
