from aiogram import Router

from bot.handlers import errors, menu, start


def setup_routers() -> Router:
    root = Router()
    root.include_routers(
        errors.router,
        start.router,
        menu.router,
    )
    return root
