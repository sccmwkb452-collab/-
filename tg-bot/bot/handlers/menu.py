from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.config import settings
from bot.database.models import Subscription, Transaction, TransactionStatus, User
from bot.keyboards.main_menu import back_to_menu_keyboard, main_menu_keyboard
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = Router(name="menu")


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, user: User) -> None:
    await callback.message.edit_text(
        text="🏠 <b>Главное меню</b>\n\nВыбери нужный раздел:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:subscription")
async def cb_subscription(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()

    if sub and sub.status.value == "active":
        text = (
            "💎 <b>Подписка</b>\n\n"
            f"✅ Активный план: <b>{sub.plan_name}</b>\n"
            f"📅 Действует до: <b>{sub.expires_at.strftime('%d.%m.%Y') if sub.expires_at else 'Бессрочно'}</b>\n\n"
            "<i>Раздел пополнения подписки будет доступен скоро.</i>"
        )
    else:
        text = (
            "💎 <b>Купить подписку</b>\n\n"
            "Подписка открывает доступ к:\n"
            "• 🎁 Эксклюзивным NFT-подаркам\n"
            "• 🚀 Приоритетной поддержке\n"
            "• 💫 Специальным предложениям\n\n"
            "<i>Оплата и тарифные планы будут доступны скоро.</i>"
        )

    await callback.message.edit_text(
        text=text,
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:nft_gifts")
async def cb_nft_gifts(callback: CallbackQuery, user: User) -> None:
    text = (
        "🎁 <b>NFT-подарки</b>\n\n"
        "В этом разделе ты сможешь:\n"
        "• 🛒 Покупать уникальные NFT-подарки\n"
        "• 📤 Дарить их друзьям в Telegram\n"
        "• 🖼 Просматривать свою коллекцию\n\n"
        "<i>Каталог NFT-подарков скоро появится здесь.</i>"
    )
    await callback.message.edit_text(
        text=text,
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:account")
async def cb_account(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    sub_result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == "active")
        .limit(1)
    )
    active_sub = sub_result.scalar_one_or_none()

    tx_count_result = await session.execute(
        select(func.count()).select_from(Transaction).where(Transaction.user_id == user.id)
    )
    tx_count = tx_count_result.scalar() or 0

    nft_count_result = await session.execute(
        select(func.count())
        .select_from(__import__("bot.database.models", fromlist=["NFTGift"]).NFTGift)
        .where(__import__("bot.database.models", fromlist=["NFTGift"]).NFTGift.owner_id == user.id)
    )
    nft_count = nft_count_result.scalar() or 0

    sub_status = f"✅ {active_sub.plan_name}" if active_sub else "❌ Нет подписки"

    text = (
        "👤 <b>Мой аккаунт</b>\n\n"
        f"👋 Имя: <b>{user.full_name}</b>\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📛 Username: {('@' + user.username) if user.username else 'не указан'}\n\n"
        f"💎 Подписка: {sub_status}\n"
        f"🎁 NFT-подарков: <b>{nft_count}</b>\n"
        f"📋 Операций: <b>{tx_count}</b>\n\n"
        f"📅 Аккаунт создан: <b>{user.created_at.strftime('%d.%m.%Y')}</b>"
    )

    await callback.message.edit_text(
        text=text,
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:history")
async def cb_history(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
    )
    transactions = result.scalars().all()

    if not transactions:
        text = (
            "📋 <b>История операций</b>\n\n"
            "У тебя пока нет операций.\n\n"
            "<i>Здесь будет отображаться история покупок и подарков.</i>"
        )
    else:
        lines = ["📋 <b>Последние операции:</b>\n"]
        type_emoji = {
            "subscription": "💎",
            "nft_purchase": "🛒",
            "nft_gift": "🎁",
            "refund": "↩️",
        }
        status_emoji = {
            "pending": "⏳",
            "completed": "✅",
            "failed": "❌",
        }
        for tx in transactions:
            emoji = type_emoji.get(tx.type.value, "💰")
            s_emoji = status_emoji.get(tx.status.value, "❓")
            lines.append(
                f"{emoji} {s_emoji} <b>{tx.amount} {tx.currency}</b> "
                f"— {tx.created_at.strftime('%d.%m.%Y')}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(
        text=text,
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery) -> None:
    text = (
        "🆘 <b>Поддержка</b>\n\n"
        "Если у тебя возникли вопросы или проблемы, свяжись с нами:\n\n"
        f"💬 Написать в поддержку: @{settings.support_username}\n\n"
        "Мы отвечаем в течение 24 часов. "
        "Укажи свой ID (<code>{}</code>) при обращении."
    )
    await callback.message.edit_text(
        text=text.format(callback.from_user.id),
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
