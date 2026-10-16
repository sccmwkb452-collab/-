"""Handles «Check payment» callback — verifies the blockchain transaction."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_kb, ton_payment_kb
from bot.ui.rich_text import RichTextBuilder
from bot.ui.templates import subscription_active
from database.models.user import User
from payments.payment_service import PaymentService
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = Router(name="payment")


@router.callback_query(F.data.startswith("pay:check:"))
async def cb_pay_check(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    """
    Triggered by the user pressing «I paid — check».
    Fetches the blockchain, verifies the tx, and activates the subscription
    only if verification passes. Does NOT activate on button press alone.
    """
    payment_comment = callback.data.removeprefix("pay:check:")

    await callback.answer("🔍 Проверяю транзакцию на блокчейне...", show_alert=False)

    result = await PaymentService(session).check_and_activate(payment_comment)
    await session.commit()

    if result.activated:
        sub = await SubscriptionService(session).get_active(db_user.id)
        if sub:
            text, entities = subscription_active(sub)
            await callback.message.edit_text(
                text=text,
                entities=entities,
                reply_markup=back_kb(),
            )
        else:
            rt = RichTextBuilder()
            rt.bold("✅ Подписка активирована!\n\n")
            rt.text("Воспользуйся кнопкой «Главное меню», чтобы продолжить.")
            t, e = rt.build()
            await callback.message.edit_text(text=t, entities=e, reply_markup=back_kb())

        logger.info(
            "Subscription activated via TON for user_id=%d comment=%s",
            db_user.id,
            payment_comment,
        )
    else:
        reason = result.reason
        rt = RichTextBuilder()
        rt.bold("⏳ Транзакция не найдена\n\n")
        if "not found" in reason.lower() or "not found" in reason:
            rt.text("Транзакция ещё не появилась в блокчейне. ")
            rt.text("Подожди 1–2 минуты и попробуй снова.")
        elif "expired" in reason.lower():
            rt.text("Окно оплаты истекло. Создай новый платёж.")
        elif "duplicate" in reason.lower() or "already" in reason.lower():
            rt.bold("⚠️ Эта транзакция уже была зачислена другому пользователю.")
        else:
            rt.text(f"Ошибка проверки: {reason}")
        t, e = rt.build()
        await callback.message.edit_text(
            text=t,
            entities=e,
            reply_markup=ton_payment_kb(payment_comment),
        )
        logger.info(
            "TON payment check failed for user_id=%d comment=%s reason=%s",
            db_user.id,
            payment_comment,
            reason,
        )
