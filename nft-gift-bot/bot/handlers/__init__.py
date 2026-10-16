from aiogram import Router

from bot.handlers import (
    account_connect,
    errors,
    gifts,
    info_support,
    menu_nav,
    profile,
    start,
    subscription,
    tdata,
)


def build_main_router() -> Router:
    root = Router(name="root")
    # Ошибки — первыми, перехватывают exceptions из всех дочерних роутеров
    root.include_router(errors.router)
    root.include_router(start.router)
    root.include_router(menu_nav.router)
    root.include_router(subscription.router)
    root.include_router(gifts.router)
    root.include_router(account_connect.router)
    root.include_router(tdata.router)
    root.include_router(profile.router)
    root.include_router(info_support.router)
    return root
