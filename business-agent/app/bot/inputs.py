"""Универсальный ввод значений: раздел регистрирует ключ, подсказку и функцию-обработчик."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.states import Input
from app.bot.ui import btn, kb

Setter = Callable[..., Awaitable[tuple[bool, str]]]


@dataclass
class InputSpec:
    prompt: str
    setter: Setter | None
    back: str  # "раздел" или "раздел:действие" (id объекта берётся из obj_id)


REGISTRY: dict[str, InputSpec] = {}


def input_field(key: str, prompt: str, back: str):
    def deco(fn: Setter) -> Setter:
        REGISTRY[key] = InputSpec(prompt, fn, back)
        return fn

    return deco


async def ask(cq: CallbackQuery, state: FSMContext, key: str, current: str | None = None, **extra: Any) -> None:
    spec = REGISTRY[key]
    await state.set_state(Input.value)
    await state.update_data(input_key=key, **extra)
    text = spec.prompt + (f"\n\nТекущее значение:\n<code>{current}</code>" if current else "")
    await cq.message.answer(text + "\n\n/cancel — отмена")
    await cq.answer()


router = Router(name="inputs")


@router.message(Input.value, F.text == "/cancel")
async def cancel_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    back = REGISTRY.get(data.get("input_key", ""), InputSpec("", None, "main")).back
    section, _, action = back.partition(":")
    await message.answer("Отменено.", reply_markup=kb(
        [btn("↩️ Вернуться в раздел", section, action or "show", int(data.get("obj_id", 0)))], back="main"))


@router.message(Input.value, F.text)
async def receive_input(message: Message, state: FSMContext, session, owner, ctx) -> None:
    data = await state.get_data()
    spec = REGISTRY.get(data.get("input_key", ""))
    if spec is None:
        await state.clear()
        return
    ok, reply = await spec.setter(session=session, owner=owner, text=message.text.strip(), data=data, ctx=ctx)
    if ok:
        await state.clear()
        section, _, action = spec.back.partition(":")
        await message.answer(reply, reply_markup=kb(
            [btn("↩️ Вернуться в раздел", section, action or "show", int(data.get("obj_id", 0)))], back="main"))
    else:
        await message.answer(f"⚠️ {reply}\nПопробуйте ещё раз или /cancel.")
