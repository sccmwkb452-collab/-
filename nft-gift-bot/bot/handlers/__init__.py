from aiogram import Router

from bot.handlers import errors, start


def build_main_router() -> Router:
    root = Router(name="root")
    # Ошибки — первыми, чтобы перехватывать exceptions из всех роутеров
    root.include_router(errors.router)
    root.include_router(start.router)
    return root
