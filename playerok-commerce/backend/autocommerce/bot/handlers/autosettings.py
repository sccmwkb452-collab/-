"""⚙️ Автонастройки — the settings menu from the owner's screenshot:
14 items, each with description, status, parameters, save, preview, test,
history, reset; plus the emergency stop of all automation."""

from __future__ import annotations

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ...services import app_settings, autosettings
from ...services.audit import Actor
from ...shared.timeutil import fmt_dt
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, confirm, esc, kb, short

router = make_router("autosettings")

STATE_ICON = {"available": "🟢", "assist": "🟡", "unavailable": "🔴"}


@router.callback_query(F.data == "as:home")
async def home(cb: CallbackQuery, session: AsyncSession) -> None:
    items = await autosettings.overview(session)
    ks = await app_settings.kill_switch(session)
    lines = ["⚙️ <b>Автонастройки</b>", SEP]
    if ks.get("active"):
        lines.append(f"🛑 <b>Аварийная остановка включена</b> ({esc(ks.get('by'))}): {esc(ks.get('reason') or 'без причины')}\n")
    for it in items:
        lines.append(f"{'✅' if it['enabled'] else '▫️'} {it['label']} — {STATE_ICON[it['integration']['state']]}")
    lines.append(
        "\n<i>✅ включено · ▫️ выключено · 🟢 работает через интеграцию · 🟡 режим подсказок оператору · 🔴 интеграция недоступна</i>"
    )
    rows = [[b(it["label"], f"as:open:{it['code']}")] for it in items]
    stop = (
        b("▶️ Снять аварийную остановку", "sec:kill:off")
        if ks.get("active")
        else b("🛑 Отключить всё (аварийно)", "as:stopall", style="danger")
    )
    rows.append([stop])
    rows.append([b("‹ Назад в меню", "home")])
    await show(cb, "\n".join(lines), kb(*rows))


def _value_text(field: autosettings.Field, value) -> str:
    if field.type == "bool":
        return "да" if value else "нет"
    if field.type == "choice":
        return dict(field.choices).get(value, str(value))
    if field.type == "multichoice":
        names = dict(field.choices)
        return ", ".join(names.get(v, v) for v in value) if value else "все"
    if field.type == "list":
        return ", ".join(map(str, value)) if value else "—"
    return short(str(value), 120) if value not in (None, "") else "—"


async def item_screen(session: AsyncSession, code: str) -> tuple[str, object]:
    f = autosettings.feature(code)
    d = await autosettings.details(session, code)
    integ = d["integration"]
    lines = [
        f"{f.label}",
        SEP,
        esc(f.description),
        "",
        f"Статус: <b>{'🟢 Включено' if d['enabled'] else '⚪️ Выключено'}</b>" + (" · 🛑 остановлено аварийно" if d["stopped"] else ""),
        f"Интеграция: <b>{integ['label']}</b>",
    ]
    if integ["state"] != "available":
        lines.append(f"<i>{esc(short(integ['reason'], 600))}</i>")
    if integ.get("assist"):
        lines.append(f"💡 Сейчас работает: {esc(integ['assist'])}")
    lines += ["", "<b>Параметры</b>"]
    for field in f.fields:
        lines.append(f"• {esc(field.label)}: <b>{esc(_value_text(field, d['config'].get(field.name)))}</b>")
    if f.safety:
        lines.append(f"\n🛡 {esc(f.safety)}")
    if d["updated_by"]:
        lines.append(f"\n✏️ Изменено: {fmt_dt(_dt(d['updated_at']))} · {esc(d['updated_by'])}")
    toggle = (
        b("⚪️ Выключить", f"as:tog:{code}:0")
        if d["enabled"]
        else (
            b("🟢 Включить", f"as:tog:{code}:1", style="success")
            if integ["state"] != "unavailable"
            else b("🔴 Интеграция недоступна", "noop")
        )
    )
    rows = [[toggle]]
    edit_buttons = [b(f"✏️ {short(field.label, 26)}", f"as:f:{code}:{field.name}") for field in f.fields]
    rows += [edit_buttons[i : i + 2] for i in range(0, len(edit_buttons), 2)]
    rows.append([b("👁 Предпросмотр", f"as:prev:{code}"), b("🧪 Тест", f"as:test:{code}")])
    rows.append([b("🕓 История", f"as:hist:{code}"), b("♻️ Сбросить", f"as:reset:{code}")])
    if code == "autoresponder":
        rows.append([b("🤖 Правила", "msg:rules"), b("🧪 Проверить вопрос", "msg:test")])
    rows.append([b("‹ Назад", "as:home"), b("🏠 Меню", "home")])
    return "\n".join(lines), kb(*rows)


def _dt(value):
    from datetime import datetime

    return datetime.fromisoformat(value) if value else None


@router.callback_query(F.data.startswith("as:open:"))
async def open_item(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await item_screen(session, cb.data.split(":", 2)[2])
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("as:tog:"))
async def toggle(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "autosettings.manage")
    _, _, code, flag = cb.data.split(":")
    await autosettings.set_enabled(session, code, flag == "1", actor)
    await cb.answer("Включено" if flag == "1" else "Выключено")
    text, markup = await item_screen(session, code)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("as:f:"))
async def edit_field(cb: CallbackQuery, session: AsyncSession, actor: Actor, state: FSMContext) -> None:
    require(actor, "autosettings.manage")
    _, _, code, name = cb.data.split(":", 3)
    f = autosettings.feature(code)
    field = next(x for x in f.fields if x.name == name)
    d = await autosettings.details(session, code)
    current = d["config"].get(name)
    if field.type == "bool":
        await autosettings.update(session, code, {name: not current}, actor)
        text, markup = await item_screen(session, code)
        await show(cb, text, markup)
        return
    if field.type in ("choice", "multichoice"):
        selected = current if isinstance(current, list) else [current]
        prefix = "as:c" if field.type == "choice" else "as:m"
        rows = [[b(("✅ " if value in selected else "▫️ ") + label, f"{prefix}:{code}:{name}:{value}")] for value, label in field.choices]
        hint = "Выберите вариант" if field.type == "choice" else "Отметьте нужные (пусто — все)"
        await show(cb, f"{f.label} → <b>{esc(field.label)}</b>\n{hint}:", kb(*rows, [b("‹ Готово", f"as:open:{code}")]))
        return
    variables = ""
    if field.type == "template":
        variables = "\n\nПеременные: " + ", ".join("{" + k + "}" for k in d["variables"])
    limits = f" ({field.min}–{field.max})" if field.type == "int" and field.min is not None else ""
    shown = esc(", ".join(map(str, current)) if isinstance(current, list) else current)
    await ask(
        cb,
        state,
        "as_value",
        f"{f.label} → <b>{esc(field.label)}</b>{limits}\nСейчас: <code>{shown}</code>{variables}"
        + ("\nСписок — через запятую." if field.type == "list" else ""),
        back=f"as:open:{code}",
        code=code,
        field=name,
    )


@on_input("as_value")
async def value_input(message: Message, ctx: dict) -> None:
    await autosettings.update(ctx["session"], ctx["code"], {ctx["field"]: message.text.strip()}, ctx["actor"])
    await ctx["state"].clear()
    text, markup = await item_screen(ctx["session"], ctx["code"])
    await message.answer("✅ Сохранено\n\n" + text, reply_markup=markup)


@router.callback_query(F.data.startswith("as:c:"))
async def set_choice(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "autosettings.manage")
    _, _, code, name, value = cb.data.split(":", 4)
    await autosettings.update(session, code, {name: value}, actor)
    text, markup = await item_screen(session, code)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("as:m:"))
async def toggle_multi(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "autosettings.manage")
    _, _, code, name, value = cb.data.split(":", 4)
    d = await autosettings.details(session, code)
    current = list(d["config"].get(name) or [])
    current = [v for v in current if v != value] if value in current else current + [value]
    await autosettings.update(session, code, {name: current}, actor)
    f = autosettings.feature(code)
    field = next(x for x in f.fields if x.name == name)
    rows = [[b(("✅ " if v in current else "▫️ ") + label, f"as:m:{code}:{name}:{v}")] for v, label in field.choices]
    await show(cb, f"{f.label} → <b>{esc(field.label)}</b>\nОтметьте нужные (пусто — все):", kb(*rows, [b("‹ Готово", f"as:open:{code}")]))


@router.callback_query(F.data.startswith("as:prev:"))
async def preview(cb: CallbackQuery, session: AsyncSession) -> None:
    code = cb.data.split(":", 2)[2]
    f = autosettings.feature(code)
    d = await autosettings.details(session, code)
    texts = []
    for field in f.fields:
        if field.type == "template":
            texts.append(f"<b>{esc(field.label)}</b>\n<code>{esc(await autosettings.preview(session, code, field.name))}</code>")
    body = "\n\n".join(texts) or "<i>У этой настройки нет текстов — параметры показаны в карточке.</i>"
    await show(
        cb, f"👁 <b>Предпросмотр: {f.label}</b>\n<i>С примером данных заказа</i>\n{SEP}\n{body}", kb([b("‹ Назад", f"as:open:{code}")])
    )
    _ = d


@router.callback_query(F.data.startswith("as:test:"))
async def test(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    code = cb.data.split(":", 2)[2]
    result = await autosettings.test(session, code, actor)
    f = autosettings.feature(code)
    lines = [f"🧪 <b>Тест: {f.label}</b>", SEP, "✅ Настройка корректна" if result["ok"] else "⚠️ Есть проблемы:"]
    lines += [f"• {esc(p)}" for p in result["problems"]]
    lines.append(f"Интеграция: {result['integration']['label']}")
    for label, text in result["texts"].items():
        lines.append(f"\n<b>{esc(label)}</b> — так увидит покупатель:\n<code>{esc(text)}</code>")
    lines.append("\n<i>Тест ничего не отправляет покупателям. Результат записан в историю.</i>")
    await show(cb, "\n".join(lines), kb([b("‹ Назад", f"as:open:{code}")]))


@router.callback_query(F.data.startswith("as:hist:"))
async def history(cb: CallbackQuery, session: AsyncSession) -> None:
    code = cb.data.split(":", 2)[2]
    d = await autosettings.details(session, code)
    icons = {"ok": "✅", "skipped": "⏭", "blocked": "🛑", "error": "⛔", "suggested": "💡"}
    lines = [f"🕓 <b>История: {d['label']}</b>", SEP]
    lines += [
        f"{icons.get(h['result'], '•')} {fmt_dt(_dt(h['at']))} · {esc(h['action'])}: {esc(short(h['message'], 90))}" for h in d["history"]
    ] or ["<i>Пока нет событий</i>"]
    if d["last_error"]:
        lines.append(f"\n⛔ Последняя ошибка: {esc(d['last_error'])}")
    await show(cb, "\n".join(lines), kb([b("‹ Назад", f"as:open:{code}")]))


@router.callback_query(F.data.regexp(r"^as:reset:[a-z_]+(:y)?$"))
async def reset(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "autosettings.manage")
    parts = cb.data.split(":")
    code = parts[2]
    if len(parts) == 3:
        text, markup = confirm(
            f"Сбросить «{autosettings.feature(code).label}» к стандартным значениям? Включение/выключение не меняется.",
            f"as:reset:{code}:y",
            f"as:open:{code}",
        )
        await show(cb, text, markup)
        return
    await autosettings.reset(session, code, actor)
    text, markup = await item_screen(session, code)
    await show(cb, "♻️ Сброшено\n\n" + text, markup)


@router.callback_query(F.data.regexp(r"^as:stopall(:y)?$"))
async def stop_all(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "security.manage")
    if not cb.data.endswith(":y"):
        text, markup = confirm(
            "Аварийно отключить ВСЕ автоматические действия? Закупки, автовыдача и подсказки остановятся, заказы будут ждать оператора.",
            "as:stopall:y",
            "as:home",
            danger=True,
        )
        await show(cb, text, markup)
        return
    count = await autosettings.emergency_disable_all(session, actor, "Аварийное отключение из Telegram")
    await cb.answer(f"Отключено настроек: {count}", show_alert=True)
    await home(cb, session)
