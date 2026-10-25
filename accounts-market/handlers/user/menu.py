"""/start, main menu, support, rules and stale buttons."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import media
from bot.callbacks import Nav, Noop
from bot.ui import Screen, show
from database.models import User
from keyboards import user as kb
from referrals.service import attach_referrer, parse_start_arg
from services.formatting import esc
from services.shop_settings import ShopSettings

router = Router(name="menu")


async def home_screen(shop: ShopSettings, is_admin: bool) -> Screen:
    text = f"⚡ <b>{esc(shop.shop_name)}</b>\n\n{esc(shop.welcome_text)}"
    return Screen(text, kb.main_menu(is_admin, shop.news_url), await media.banner("home", shop.shop_name))


@router.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
    user: User,
    user_is_new: bool,
    shop: ShopSettings,
    is_admin: bool,
) -> None:
    await state.clear()
    code = parse_start_arg(command.args)
    if code:
        referrer = await attach_referrer(session, user, code, is_new=user_is_new)
        if referrer is not None:
            await session.commit()
            try:
                await message.bot.send_message(
                    referrer.id,
                    "🎁 По вашей ссылке зарегистрировался новый пользователь. "
                    "Бонус начислится после его покупки.",
                )
            except Exception:  # the inviter may have blocked the bot
                pass
    await show(message, await home_screen(shop, is_admin))


@router.message(Command("menu"))
async def menu_command(message: Message, state: FSMContext, shop: ShopSettings, is_admin: bool) -> None:
    await state.clear()
    await show(message, await home_screen(shop, is_admin))


@router.callback_query(Nav.filter(F.to == "home"))
async def home(callback: CallbackQuery, state: FSMContext, shop: ShopSettings, is_admin: bool) -> None:
    await state.clear()
    await show(callback, await home_screen(shop, is_admin))


@router.callback_query(Nav.filter(F.to == "support"))
async def support(callback: CallbackQuery, shop: ShopSettings) -> None:
    lines = [
        "🆘 <b>Поддержка</b>",
        "",
        "Поможем с оплатой, выдачей товара и любыми вопросами по заказу.",
        "Чтобы ответ был быстрее, сразу укажите номер заказа (например, <code>AM-000123</code>) "
        "и опишите проблему.",
    ]
    if not shop.support_url:
        lines += ["", "Контакт поддержки пока не указан администратором."]
    await show(
        callback,
        Screen("\n".join(lines), kb.support(shop.support_url, shop.news_url), await media.banner("support", shop.shop_name)),
    )


@router.message(Command("support"))
async def support_command(message: Message, shop: ShopSettings) -> None:
    text = "🆘 <b>Поддержка</b>\n\nУкажите номер заказа и опишите вопрос."
    await show(message, Screen(text, kb.support(shop.support_url, shop.news_url), await media.banner("support", shop.shop_name)))


@router.callback_query(Nav.filter(F.to == "rules"))
async def rules(callback: CallbackQuery, shop: ShopSettings) -> None:
    text = f"📜 <b>Правила магазина</b>\n\n{esc(shop.rules_text)}"
    await show(callback, Screen(text, kb.rules(shop.support_url), await media.banner("rules", shop.shop_name)))


@router.callback_query(Noop.filter())
async def noop(callback: CallbackQuery) -> None:
    pass  # page counter and spacers: CallbackAnswerMiddleware answers silently
