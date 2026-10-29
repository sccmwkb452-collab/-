from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.ai.instructions import get_active_config
from app.ai.prompts import HARD_RULES
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.inputs import ask, input_field
from app.bot.ui import btn, kb
from app.core.audit import audit

router = Router(name="ai_settings")
EFFORTS = ["low", "medium", "high"]


@input_field("ai_style", "Опишите желаемый стиль общения агента в ваших чатах (тон, обращение на «ты»/«вы», длина "
             "ответов, эмодзи). Глобальные правила задаёт администратор.", "ai")
async def ai_style(session, owner, text, **_):
    owner.style_notes = text[:3000]
    await audit(session, "ai_style_changed", owner_id=owner.id, actor="user")
    return True, "Стиль сохранён."


@input_field("ai_lang", "Основной язык общения (например <code>ru</code>, <code>en</code>):", "ai")
async def ai_lang(session, owner, text, **_):
    owner.language = text[:16]
    return True, f"Язык: {escape(owner.language)}"


@router.callback_query(Cb.filter(F.s == "ai"))
async def ai_section(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner, ctx, is_admin):
    a = callback_data.a
    if a in ("f_ai_style", "f_ai_lang"):
        return await ask(cq, state, a[2:], escape(owner.style_notes if a == "f_ai_style" else owner.language))
    if a == "effort":
        cur = owner.ai_effort or ctx.settings.ai_effort
        owner.ai_effort = EFFORTS[(EFFORTS.index(cur) + 1) % 3] if cur in EFFORTS else "medium"
    if a == "rules":
        return await show(cq, "<b>Неизменяемые правила агента</b>\n\n" + escape(HARD_RULES), kb(back="ai"))
    cfg = await get_active_config(session)
    text = (
        "<b>🧠 Настройки ИИ</b>\n"
        f"Модель: {escape(ctx.settings.ai_model)} {'✅' if ctx.llm else '⚠️ не настроена (ANTHROPIC_API_KEY)'}\n"
        f"Глубина рассуждений (effort): {owner.ai_effort or ctx.settings.ai_effort}\n"
        f"Язык: {escape(owner.language)}\n"
        f"Ваш стиль: {escape(owner.style_notes[:300] or '—')}\n"
        f"Глобальные инструкции администратора: {('версия ' + str(cfg.version)) if cfg else 'не заданы'}\n\n"
        "Агент всегда честно сообщает, что он ИИ-ассистент, если его об этом спрашивают, и не выдумывает данные."
    )
    rows = [[btn("🎚 Effort", "ai", "effort"), btn("🌐 Язык", "ai", "f_ai_lang")],
            [btn("✍️ Мой стиль", "ai", "f_ai_style"), btn("🛡 Неизменяемые правила", "ai", "rules")]]
    if is_admin:
        rows.append([btn("🛡 Глобальные инструкции (админ)", "admin")])
    await show(cq, text, kb(*rows))
