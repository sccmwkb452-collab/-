"""Broadcast handler and background task for admin panel."""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, update

from admin.keyboards import broadcast_confirm_kb, cancel_kb, main_panel_kb
from admin.states import AdminFSM
from bot.filters.admin import AdminFilter
from bot.ui.rich_text import RichTextBuilder
from database.models.user import User
from database.repositories.audit_repo import AuditRepository
from database.session import AsyncSessionFactory

logger = logging.getLogger(__name__)

broadcast_router = Router(name="admin_broadcast")
broadcast_router.message.filter(AdminFilter())
broadcast_router.callback_query.filter(AdminFilter())


# ── Entry ─────────────────────────────────────────────────────────────────────

@broadcast_router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminFSM.enter_broadcast_text)
    text = "📢 <b>Рассылка</b>\n\nВведите текст сообщения для рассылки всем пользователям:"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb())
    await callback.answer()


# ── FSM: receive text ─────────────────────────────────────────────────────────

@broadcast_router.message(AdminFSM.enter_broadcast_text)
async def fsm_broadcast_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Текст не может быть пустым. Попробуйте ещё раз.")
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(AdminFSM.confirm_broadcast)

    preview = (
        "📢 <b>Предпросмотр рассылки:</b>\n\n"
        f"{text}\n\n"
        "Отправить всем пользователям?"
    )
    await message.answer(preview, parse_mode="HTML", reply_markup=broadcast_confirm_kb())


# ── FSM: confirm + launch background task ────────────────────────────────────

@broadcast_router.callback_query(F.data == "adm:broadcast:send", AdminFSM.confirm_broadcast)
async def cb_broadcast_send(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    broadcast_text: str = data.get("broadcast_text", "")
    await state.clear()

    if not broadcast_text:
        await callback.answer("Текст рассылки потерян, попробуйте снова.", show_alert=True)
        return

    admin_tg_id = callback.from_user.id
    await callback.answer("Рассылка запущена…", show_alert=False)

    b = RichTextBuilder()
    b.plain("📢 ")
    b.bold("Рассылка запущена")
    b.plain("\nРезультат придёт сюда по завершению.")
    t, e = b.build()
    await callback.message.edit_text(t, entities=e, reply_markup=main_panel_kb())

    asyncio.create_task(
        _run_broadcast(bot=bot, text=broadcast_text, admin_tg_id=admin_tg_id),
        name=f"broadcast_{admin_tg_id}",
    )


# ── Background broadcast task ─────────────────────────────────────────────────

async def _run_broadcast(bot: Bot, text: str, admin_tg_id: int) -> None:
    """Send text to all non-blocked users. Runs in its own DB session."""
    sent = 0
    failed = 0
    blocked_ids: list[int] = []

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(User.telegram_id).where(User.is_blocked == False)  # noqa: E712
        )
        user_ids: list[int] = list(result.scalars().all())

    for tg_id in user_ids:
        try:
            await bot.send_message(tg_id, text)
            sent += 1
        except TelegramForbiddenError:
            blocked_ids.append(tg_id)
            failed += 1
        except Exception as exc:
            logger.warning("Broadcast send error tg_id=%d: %s", tg_id, exc)
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msg/sec — stays within Telegram limits

    # Batch-update newly blocked users
    if blocked_ids:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                await session.execute(
                    update(User)
                    .where(User.telegram_id.in_(blocked_ids))
                    .values(is_blocked=True)
                )
        logger.info("Marked %d users as blocked after broadcast", len(blocked_ids))

    # Audit log
    async with AsyncSessionFactory() as session:
        async with session.begin():
            audit = AuditRepository(session)
            await audit.log(
                admin_tg_id=admin_tg_id,
                action="broadcast",
                details=f"sent={sent} failed={failed} newly_blocked={len(blocked_ids)}",
            )

    # Report back to admin
    report = (
        f"📢 <b>Рассылка завершена</b>\n\n"
        f"✅ Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>\n"
        f"🚫 Заблокировавших бота: <b>{len(blocked_ids)}</b>"
    )
    try:
        await bot.send_message(admin_tg_id, report, parse_mode="HTML")
    except Exception as exc:
        logger.error("Could not send broadcast report to admin %d: %s", admin_tg_id, exc)
