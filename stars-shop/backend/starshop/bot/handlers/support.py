from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.models import User
from ...services import support
from ...services.app_settings import RuntimeSettings
from ...shared.errors import AppError
from ..keyboards import main_menu, support_waiting, webapp_button, with_back

router = Router(name="support")


class SupportFlow(StatesGroup):
    waiting_message = State()


def support_text(runtime: RuntimeSettings) -> str:
    s = runtime.content.support
    lines = ["💬 <b>Поддержка</b>", ""]
    if s.telegram:
        lines.append(f"Telegram: @{escape(s.telegram.lstrip('@'))}")
    if s.email:
        lines.append(f"Email: {escape(s.email)}")
    lines += [
        escape(s.hours),
        escape(s.response_time),
        "",
        "Опишите проблему одним сообщением — мы ответим прямо в этот чат. Если вопрос по заказу, укажите его номер.",
    ]
    lines.append("\n🔒 Мы никогда не просим пароль, код входа или данные карты.")
    return "\n".join(lines)


@router.callback_query(F.data == "menu:support")
async def open_support(callback: CallbackQuery, state: FSMContext, runtime: RuntimeSettings) -> None:
    await state.set_state(SupportFlow.waiting_message)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(support_text(runtime), reply_markup=support_waiting())


@router.message(Command("support"))
async def support_cmd(message: Message, state: FSMContext, runtime: RuntimeSettings) -> None:
    await state.set_state(SupportFlow.waiting_message)
    await message.answer(support_text(runtime), reply_markup=support_waiting())


@router.callback_query(F.data == "support:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        await callback.message.edit_text("Хорошо, если понадобится помощь — нажмите «💬 Поддержка».", reply_markup=main_menu())


@router.message(SupportFlow.waiting_message, F.text, ~F.text.startswith("/"))
async def receive(message: Message, state: FSMContext, session: AsyncSession, db_user: User, runtime: RuntimeSettings) -> None:
    text = (message.text or "").strip()
    try:
        ticket = await support.latest_open_ticket(session, db_user)
        if ticket is not None:
            await support.add_user_message(session, ticket, text)
        else:
            ticket = await support.create_ticket(session, db_user, text, runtime)
    except AppError as exc:
        await message.answer(f"⚠️ {escape(exc.message)}")
        return
    await state.clear()
    await message.answer(
        f"✅ Сообщение принято, обращение <b>#{ticket.id}</b>. Ответ придёт в этот чат.",
        reply_markup=with_back([webapp_button("Мои обращения", "support")]),
    )


@router.message(SupportFlow.waiting_message, ~F.text)
async def non_text(message: Message) -> None:
    await message.answer("Пожалуйста, опишите вопрос текстом. Скриншоты можно приложить позже по запросу поддержки.")
