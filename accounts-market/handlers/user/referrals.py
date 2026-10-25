"""Referral program screen and reward history."""

from __future__ import annotations

import math
from urllib.parse import quote

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot import media
from bot.callbacks import Nav, RefHistory
from bot.ui import Screen, show
from database.models import User, format_order_number
from keyboards import user as kb
from referrals import service as referrals
from services import users
from services.formatting import dt, esc, money
from services.shop_settings import ShopSettings

router = Router(name="referrals")
HISTORY_PAGE = 10


@router.callback_query(Nav.filter(F.to == "ref"))
async def referral(callback: CallbackQuery, session: AsyncSession, user: User, shop: ShopSettings, bot_username: str) -> None:
    link = referrals.referral_link(bot_username, user)
    stats = await users.profile_stats(session, user.id)
    if shop.referral_percent > 0:
        condition = "с первой покупки" if shop.referral_mode == "first" else "с каждой покупки"
        reward = f"Вы получаете <b>{shop.referral_percent:g}%</b> {condition} приглашённого друга на свой баланс."
    else:
        reward = "Сейчас вознаграждения не начисляются, но приглашения засчитываются."
    text = (
        "🎁 <b>Реферальная программа</b>\n\n"
        f"{reward}\n\n"
        f"🔗 Ваша ссылка:\n<code>{esc(link)}</code>\n\n"
        f"👥 Приглашено: <b>{stats.referrals}</b>\n"
        f"🛒 С покупками: <b>{stats.referrals_with_purchases}</b>\n"
        f"💸 Заработано: <b>{money(stats.referral_earned)}</b>\n\n"
        "Бонус начисляется только за новых пользователей. Приглашать самого себя нельзя."
    )
    share = f"https://t.me/share/url?url={quote(link)}&text={quote(f'{shop.shop_name}: магазин цифровых товаров')}"
    await show(callback, Screen(text, kb.referral(share, link), await media.banner("referral", shop.shop_name)))


@router.callback_query(RefHistory.filter())
async def history(callback: CallbackQuery, callback_data: RefHistory, session: AsyncSession, user: User) -> None:
    page = max(callback_data.page, 0)
    rows, total = await referrals.reward_history(session, user.id, HISTORY_PAGE, page * HISTORY_PAGE)
    lines = ["🧾 <b>История начислений</b>", ""]
    for r in rows:
        lines.append(f"🎁 <b>+{money(r.amount)}</b> · заказ {format_order_number(r.order_id)}\n<i>{dt(r.created_at)}</i>")
    if not rows:
        lines.append("Начислений пока нет. Поделитесь ссылкой с друзьями!")
    pages = max(1, math.ceil(total / HISTORY_PAGE))
    await show(
        callback,
        Screen("\n".join(lines), kb.paged(lambda n: RefHistory(page=n), page, pages, kb.btn("◀️ Назад", Nav(to="ref")))),
    )
