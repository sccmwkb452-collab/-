from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.bot import texts
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.handlers.common import respond
from nft_gift_bot.keyboards.main import main_menu
from nft_gift_bot.services.settings_service import SettingsService

router = Router(name="start")


@router.message(CommandStart())
@router.message(Command("menu"))
async def start(message: Message, session: AsyncSession, settings: Settings, emoji: dict, state: FSMContext) -> None:
    await state.clear()
    price = await SettingsService(session, settings).subscription_price_ton()
    await respond(message, texts.welcome(emoji, price), main_menu())


@router.message(Command("help"))
async def help_(message: Message, emoji: dict) -> None:
    await respond(
        message,
        texts.notice(
            emoji, "brand", "Как это работает",
            "1. Оформите подписку в TON.\n"
            "2. Подключите свой аккаунт через Telegram Business.\n"
            "3. Выберите NFT-подарок и получателя.\n"
            "4. Подтвердите передачу кнопкой — без подтверждения бот ничего не передаёт.\n\n"
            "Команды: /menu, /transfer <номер> <@получатель>",
        ),
        main_menu(),
    )
