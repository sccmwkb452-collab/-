from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.database.models import User
from bot.keyboards.main_menu import main_menu_keyboard

router = Router(name="start")

WELCOME_TEXT = """
✨ <b>Добро пожаловать в NFT Gift Bot!</b>

Привет, <b>{name}</b>! 👋

Здесь ты можешь:
• 💎 Оформить подписку и получить доступ к эксклюзивным возможностям
• 🎁 Покупать и дарить уникальные NFT-подарки
• 📊 Отслеживать историю своих операций

<i>Выбери нужный раздел в меню ниже:</i>
"""


@router.message(CommandStart())
async def cmd_start(message: Message, user: User) -> None:
    await message.answer(
        text=WELCOME_TEXT.format(name=user.full_name),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, user: User) -> None:
    await message.answer(
        text="🏠 <b>Главное меню</b>\n\nВыбери нужный раздел:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
