"""Telegram-бот «Парсер NFT-подарков».

Запуск:
    BOT_TOKEN=123:ABC python bot.py

Переменные окружения:
    BOT_TOKEN          токен от @BotFather (обязательно)
    ADMIN_IDS          ID админов через запятую (по умолчанию 8790784360)
    DB_PATH            файл базы SQLite (по умолчанию gifts.db)
    PARSE_CONCURRENCY  сколько страниц парсить параллельно (по умолчанию 5)
    PARSE_PROXY        HTTP-прокси для парсинга t.me (необязательно)

Пользователь: /start → «🔍 Парсинг» → коллекция → модель → список NFT с владельцами.
Админ: /admin → статистика, рассылка, обязательная подписка, загрузка базы из TXT.
"""
import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent

from gift_bot import admin, subscription, user
from gift_bot.config import load_config
from gift_bot.db import Database
from gift_parser.parser import GiftParser


async def main() -> None:
    config = load_config()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  RotatingFileHandler("bot.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")],
    )
    db = Database(config.db_path)
    parser = GiftParser(concurrency=config.concurrency, proxy=config.proxy)
    bot = Bot(config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    dp = Dispatcher(config=config, db=db, parser=parser)
    middleware = subscription.SubscriptionMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    dp.include_routers(subscription.router, admin.router, user.router)

    @dp.errors(ExceptionTypeFilter(TelegramBadRequest))
    async def stale_button(event: ErrorEvent) -> bool:
        # Кнопку нажали, пока бот перезапускался, — ответить уже нельзя, это не ошибка.
        if "query is too old" in str(event.exception):
            return True
        raise event.exception

    await bot.set_my_commands([BotCommand(command="start", description="Главное меню")])
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(
                [BotCommand(command="start", description="Главное меню"),
                 BotCommand(command="admin", description="Админ-панель")],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:  # админ ещё не писал боту
            pass

    try:
        async with parser:
            await dp.start_polling(bot)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
