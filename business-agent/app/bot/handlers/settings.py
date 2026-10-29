from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.inputs import ask, input_field
from app.bot.ui import btn, kb, onoff
from app.core.audit import audit

router = Router(name="settings")


def _int_field(key, prompt, attr, lo, hi, back="settings"):
    @input_field(key, prompt, back)
    async def setter(session, owner, text, **_):
        if not text.isdigit() or not lo <= int(text) <= hi:
            return False, f"Нужно число от {lo} до {hi}"
        setattr(owner, attr, int(text))
        await audit(session, "settings_changed", owner_id=owner.id, actor="user", field=attr, value=text)
        return True, "Сохранено."


_int_field("set_retention", "Сколько дней хранить историю переписок (1–3650)?", "history_retention_days", 1, 3650)
_int_field("set_out_daily", "Максимум первых обращений в сутки (0–200)?", "outreach_daily_limit", 0, 200)
_int_field("set_out_interval", "Минимальная пауза между обращениями, секунд (30–86400)?", "outreach_min_interval_seconds", 30, 86400)
_int_field("set_recontact", "Не обращаться повторно к контакту раньше чем через N дней (1–3650)?", "recontact_cooldown_days", 1, 3650)


@input_field("set_takeover", "Команда, которой вы в любом чате переключаете диалог в ручной режим "
             "(по умолчанию <code>сутпасмотри</code>). Одно слово, 4–64 символа:", "settings")
async def set_takeover(session, owner, text, **_):
    if " " in text or not 4 <= len(text) <= 64:
        return False, "Одно слово, 4–64 символа"
    owner.takeover_command = text
    await audit(session, "settings_changed", owner_id=owner.id, actor="user", field="takeover_command")
    return True, f"Команда: <code>{escape(text)}</code>"


@router.callback_query(Cb.filter(F.s == "settings"))
async def settings_section(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner):
    a = callback_data.a
    if a.startswith("f_"):
        return await ask(cq, state, a[2:])
    toggles = {"t_history": "store_history", "t_media": "store_media_files", "t_approval": "outreach_requires_approval"}
    if a in toggles:
        setattr(owner, toggles[a], not getattr(owner, toggles[a]))
        await audit(session, "settings_changed", owner_id=owner.id, actor="user", field=toggles[a])
    text = (
        "<b>⚙️ Настройки</b>\n\n<b>Приватность</b>\n"
        f"Хранить полную историю переписок: {onoff(owner.store_history)} (выкл — только последние сообщения для контекста)\n"
        f"Срок хранения истории: {owner.history_retention_days} дн.\n"
        f"Сохранять медиафайлы на диск: {onoff(owner.store_media_files)} (иначе — только file_id и описание)\n\n"
        "<b>Обращения</b>\n"
        f"Одобрять каждое обращение вручную: {onoff(owner.outreach_requires_approval)}\n"
        f"Лимит в сутки: {owner.outreach_daily_limit}, пауза: {owner.outreach_min_interval_seconds} с\n"
        f"Повторно не раньше чем через: {owner.recontact_cooldown_days} дн.\n"
        "Отказавшимся от общения агент не пишет никогда.\n\n"
        f"<b>Ручной режим</b>: команда <code>{escape(owner.takeover_command)}</code>"
    )
    await show(cq, text, kb(
        [btn("🗂 История вкл/выкл", "settings", "t_history"), btn("⏳ Срок хранения", "settings", "f_set_retention")],
        [btn("🖼 Сохранять медиа", "settings", "t_media")],
        [btn("✋ Одобрение обращений", "settings", "t_approval"), btn("📮 Лимит в сутки", "settings", "f_set_out_daily")],
        [btn("⏱ Пауза между обращениями", "settings", "f_set_out_interval"), btn("🔁 Повторно через", "settings", "f_set_recontact")],
        [btn("🙋 Команда ручного режима", "settings", "f_set_takeover")],
    ))
