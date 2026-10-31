from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.ai.state import DealState
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.inputs import ask, input_field
from app.bot.ui import btn, kb, onoff
from app.core.audit import audit
from app.db.models import Conversation, ConversationMode

router = Router(name="agent")
MODE_RU = {"auto": "🤖 авто", "manual": "🙋 ручной", "review": "🧑‍💼 ждёт человека"}


@input_field("owner_pause", "Через сколько минут после вашего ручного сообщения агент снова может отвечать в этом чате? (0–1440)", "agent")
async def set_owner_pause(session, owner, text, **_):
    if not text.isdigit() or not 0 <= int(text) <= 1440:
        return False, "Нужно число от 0 до 1440"
    owner.owner_pause_minutes = int(text)
    return True, f"Пауза после ручного сообщения: {text} мин."


async def render(session, owner, ctx):
    convs = (await session.scalars(select(Conversation).where(Conversation.owner_id == owner.id)
                                   .order_by(Conversation.updated_at.desc()).limit(12))).all()
    lines = [
        "<b>🤖 ИИ-агент</b>",
        f"Автоматическое ведение переписок: {onoff(owner.agent_enabled)}",
        f"Пауза после вашего ручного сообщения: {owner.owner_pause_minutes} мин.",
        f"Команда ручного режима в чате: <code>{escape(owner.takeover_command)}</code>",
        "" if ctx.llm else "⚠️ ИИ не настроен — задайте ANTHROPIC_API_KEY или OPENAI_API_KEY.",
        "<b>Последние диалоги:</b>" if convs else "Диалогов пока нет.",
    ]
    rows = [[btn("⛔️ Выключить агента" if owner.agent_enabled else "✅ Включить агента", "agent", "toggle")],
            [btn("⏱ Пауза после ручного ответа", "agent", "pause_min")]]
    for c in convs:
        st = DealState.load(c.state)
        name = c.contact.display_name or (f"@{c.contact.username}" if c.contact.username else str(c.chat_id))
        lines.append(f"• {escape(name)} — {MODE_RU.get(c.mode, c.mode)}, этап {st.conversation_stage}")
        if c.mode != ConversationMode.AUTO:
            rows.append([btn(f"▶️ Авто: {name[:24]}", "agent", "auto", c.id)])
        else:
            rows.append([btn(f"🙋 Вручную: {name[:24]}", "agent", "manual", c.id)])
    return "\n".join(lines), kb(*rows)


@router.callback_query(Cb.filter(F.s == "agent"))
async def agent_section(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner, ctx):
    a = callback_data.a
    if a == "toggle":
        owner.agent_enabled = not owner.agent_enabled
        await audit(session, "agent_toggle", owner_id=owner.id, actor="user", enabled=owner.agent_enabled)
    elif a == "pause_min":
        return await ask(cq, state, "owner_pause", str(owner.owner_pause_minutes))
    elif a in ("auto", "manual"):
        conv = await session.get(Conversation, callback_data.i)
        if conv is None or conv.owner_id != owner.id:
            return await cq.answer("Диалог не найден", show_alert=True)
        conv.mode = ConversationMode.AUTO if a == "auto" else ConversationMode.MANUAL
        conv.mode_reason = "панель"
        if a == "auto":
            st = DealState.load(conv.state)
            st.requires_human_review, st.human_review_reason = False, None
            conv.state = st.dump()
            conv.last_owner_message_at = None
        else:
            ctx.business._cancel_pending(conv.id)
        await audit(session, "conversation_mode", owner_id=owner.id, actor="user", conversation_id=conv.id, mode=a)
    text, markup = await render(session, owner, ctx)
    await show(cq, text, markup)
