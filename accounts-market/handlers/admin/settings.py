"""Admin: shop settings."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy.ext.asyncio import AsyncSession

from admin.states import SettingEdit
from bot.callbacks import Adm
from bot.ui import Screen, show
from keyboards import admin as akb
from keyboards.user import btn, rows
from services import shop_settings
from services.audit import log_action
from services.formatting import clip, esc

router = Router(name="admin_settings")


async def settings_screen(session: AsyncSession) -> Screen:
    raw = await shop_settings.load_raw(session)
    lines = ["⚙️ <b>Настройки магазина</b>", ""]
    buttons = []
    for d in shop_settings.SETTINGS.values():
        value = raw[d.key] or "—"
        if d.key == "referral_percent":
            value += "%"
        if d.key == "min_topup":
            value += " ₽"
        lines.append(f"<b>{d.title}</b>: {esc(clip(value, 70))}")
        buttons.append(btn(d.title, Adm(s="sete", v=d.key)))
    kb = rows(*[buttons[i : i + 2] for i in range(0, len(buttons), 2)], [akb.ADMIN_HOME])
    return Screen("\n".join(lines), kb)


@router.callback_query(Adm.filter(F.s == "set"))
async def settings(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await show(callback, await settings_screen(session))


@router.callback_query(Adm.filter(F.s == "sete"))
async def edit(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext, callback_answer: CallbackAnswer) -> None:
    d = shop_settings.SETTINGS.get(callback_data.v)
    if d is None:
        callback_answer.text = "Неизвестная настройка"
        return
    raw = await shop_settings.load_raw(session)
    await state.set_state(SettingEdit.value)
    await state.update_data(key=d.key)
    text = (
        f"⚙️ <b>{d.title}</b>\n\nСейчас:\n<blockquote>{esc(raw[d.key] or '—')}</blockquote>\n\n"
        f"Отправьте новое значение. {esc(d.hint)}."
    )
    lines = []
    if d.optional:
        lines.append([btn("🧹 Очистить", Adm(s="setclr", v=d.key))])
    lines.append([btn("✖️ Отмена", Adm(s="set"))])
    await show(callback, Screen(text, rows(*lines)))


@router.message(SettingEdit.value, F.text)
async def save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    key = (await state.get_data())["key"]
    d = shop_settings.SETTINGS[key]
    try:
        value = d.validate(message.text)
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}", reply_markup=akb.cancel("set"))
        return
    await shop_settings.save(session, key, value)
    await log_action(session, message.from_user.id, "setting", key, clip(value, 300))
    await session.commit()
    await state.clear()
    await message.answer(f"✅ {d.title}: сохранено")
    await show(message, await settings_screen(session))


@router.callback_query(Adm.filter(F.s == "setclr"))
async def clear(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext) -> None:
    d = shop_settings.SETTINGS.get(callback_data.v)
    if d is not None and d.optional:
        await shop_settings.save(session, d.key, "")
        await log_action(session, callback.from_user.id, "setting", d.key, "")
        await session.commit()
    await state.clear()
    await show(callback, await settings_screen(session))
