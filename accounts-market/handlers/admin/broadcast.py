"""Admin: broadcasts with preview, confirmation and delivery stats."""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from admin import broadcast as engine
from admin.states import BroadcastForm
from bot.callbacks import Adm
from bot.ui import Screen, show
from database.models import Broadcast, BroadcastStatus
from keyboards import admin as akb
from keyboards.user import btn, rows
from services.audit import log_action
from services.formatting import dt

router = Router(name="admin_broadcast")
log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()


@router.callback_query(Adm.filter(F.s == "bc"))
async def broadcasts(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    items = (await session.execute(select(Broadcast).order_by(Broadcast.id.desc()).limit(8))).scalars()
    buttons = [
        (f"{'⏳' if b.status == BroadcastStatus.RUNNING else '✅'} #{b.id} · {dt(b.created_at)} · {b.sent}/{b.total}", Adm(s="bcv", id=b.id))
        for b in items
    ]
    recipients = await engine.recipients_count(session)
    text = (
        "📢 <b>Рассылки</b>\n\n"
        f"Получателей сейчас: {recipients} (без ограниченных и заблокировавших бота).\n"
        "Ниже последние рассылки."
    )
    await show(callback, Screen(text, akb.listing(buttons, 0, 1, None, [[btn("✍️ Новая рассылка", Adm(s="bcnew"), style="primary")]])))


@router.callback_query(Adm.filter(F.s == "bcnew"))
async def new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BroadcastForm.message)
    text = (
        "✍️ <b>Новая рассылка</b>\n\n"
        "Отправьте сообщение для рассылки: текст, фото или видео с подписью. "
        "Форматирование сохранится. Затем вы увидите предпросмотр."
    )
    await show(callback, Screen(text, akb.cancel("bc")))


@router.message(BroadcastForm.message)
async def preview(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    recipients = await engine.recipients_count(session)
    await message.answer("👁 <b>Предпросмотр</b>: так сообщение увидят пользователи ⬇️")
    await message.bot.copy_message(message.chat.id, message.chat.id, message.message_id)
    await message.answer(
        f"Отправить рассылку {recipients} пользователям?",
        reply_markup=rows(
            [btn("🚀 Отправить", Adm(s="bcsend"), style="success")],
            [btn("✏️ Изменить", Adm(s="bcnew")), btn("✖️ Отмена", Adm(s="bc"))],
        ),
    )


@router.callback_query(Adm.filter(F.s == "bcsend"))
async def send(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    sm: async_sessionmaker[AsyncSession],
    callback_answer: CallbackAnswer,
) -> None:
    data = await state.get_data()
    if "message_id" not in data:
        callback_answer.text, callback_answer.show_alert = "Сначала подготовьте сообщение", True
        return
    await state.clear()  # a second tap finds no draft and sends nothing
    bc = Broadcast(
        admin_id=callback.from_user.id,
        source_chat_id=data["chat_id"],
        source_message_id=data["message_id"],
        status=BroadcastStatus.RUNNING,
        total=await engine.recipients_count(session),
    )
    session.add(bc)
    await session.flush()
    await log_action(session, callback.from_user.id, "broadcast_start", f"broadcast:{bc.id}", f"total={bc.total}")
    await session.commit()

    bot = callback.bot

    async def worker() -> None:
        try:
            result = await engine.run(bot, sm, bc.id)
            await bot.send_message(
                callback.from_user.id,
                f"✅ Рассылка #{result.id} завершена\nДоставлено: {result.sent}\n"
                f"Заблокировали бота: {result.blocked}\nОшибок: {result.failed}",
                reply_markup=rows([btn("📊 Подробнее", Adm(s="bcv", id=result.id))]),
            )
        except Exception:
            log.exception("broadcast %s failed", bc.id)

    task = asyncio.create_task(worker())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    await show(callback, await broadcast_screen(session, bc.id))


async def broadcast_screen(session: AsyncSession, bid: int) -> Screen:
    b = await session.get(Broadcast, bid, populate_existing=True)
    status = "⏳ идёт отправка" if b.status == BroadcastStatus.RUNNING else "✅ завершена"
    text = (
        f"📢 <b>Рассылка #{b.id}</b>\n\n"
        f"Статус: {status}\n"
        f"Получателей: {b.total}\n"
        f"Доставлено: {b.sent}\n"
        f"Заблокировали бота: {b.blocked}\n"
        f"Ошибок: {b.failed}\n"
        f"Создана: {dt(b.created_at)}\n"
        f"Завершена: {dt(b.finished_at)}"
    )
    return Screen(text, rows([btn("🔄 Обновить", Adm(s="bcv", id=b.id))], [akb.back("bc", "◀️ К рассылкам")]))


@router.callback_query(Adm.filter(F.s == "bcv"))
async def view(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    if await session.get(Broadcast, callback_data.id) is None:
        callback_answer.text = "Рассылка не найдена"
        return
    await show(callback, await broadcast_screen(session, callback_data.id))
