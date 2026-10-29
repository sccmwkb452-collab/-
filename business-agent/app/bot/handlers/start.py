from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.ui import btn, kb, main_menu, onoff
from app.core.audit import audit
from app.db.models import BusinessConnectionRecord, Owner
from app.trading.guard import get_active_trade_bot

router = Router(name="start")

CONNECT_GUIDE = """\
<b>Как подключить Telegram Business</b>
1. Нужен Telegram Premium (Telegram для бизнеса).
2. Откройте Telegram → Настройки → <b>Telegram для бизнеса</b> → <b>Чат-боты</b>.
3. Введите <code>@{username}</code> и выберите чаты, с которыми работает агент.
4. Включите права: <b>отвечать на сообщения</b> и <b>читать сообщения</b>.
   Для команды «сутпасмотри» включите также <b>удаление сообщений</b>.
5. Бот пришлёт подтверждение с перечнем выданных прав.

🔐 Бот никогда не спрашивает пароль, код входа или другие секреты — не отправляйте их сюда.
Если в настройках бота не включён Business Mode, администратор бота включает его в @BotFather → Bot Settings → Business Mode."""


async def home_text(session, owner: Owner, ctx) -> str:
    connections = await session.scalar(select(func.count(BusinessConnectionRecord.id)).where(
        BusinessConnectionRecord.owner_id == owner.id, BusinessConnectionRecord.is_enabled.is_(True)))
    bot = await get_active_trade_bot(session, owner.id)
    return (
        f"👋 <b>Панель ИИ-агента</b>\n\n"
        f"Агент: {onoff(owner.agent_enabled)}{' · ⏸ пауза' if owner.paused else ''}\n"
        f"Business-подключений: {connections}\n"
        f"Торговый бот: {('@' + escape(bot.bot_username)) if bot else 'не выбран'}\n"
        f"ИИ: {'настроен (' + escape(ctx.settings.ai_model) + ')' if ctx.llm else '⚠️ не настроен (ANTHROPIC_API_KEY)'}"
    )


@router.message(CommandStart())
@router.message(Command("menu"))
async def start(message: Message, state: FSMContext, session, owner, ctx, is_admin) -> None:
    await state.clear()
    await message.answer(await home_text(session, owner, ctx), reply_markup=main_menu(owner, is_admin))
    has_conn = await session.scalar(select(func.count(BusinessConnectionRecord.id)).where(
        BusinessConnectionRecord.owner_id == owner.id))
    if not has_conn:
        me = await message.bot.me()
        await message.answer(CONNECT_GUIDE.format(username=me.username))


@router.callback_query(Cb.filter(F.s == "main"))
async def main(cq: CallbackQuery, state: FSMContext, session, owner, ctx, is_admin) -> None:
    await state.clear()
    await show(cq, await home_text(session, owner, ctx), main_menu(owner, is_admin))


@router.callback_query(Cb.filter(F.s.in_({"pause", "resume"})))
async def pause_resume(cq: CallbackQuery, callback_data: Cb, session, owner, ctx, is_admin) -> None:
    owner.paused = callback_data.s == "pause"
    await audit(session, "work_paused" if owner.paused else "work_resumed", owner_id=owner.id, actor="user")
    await show(cq, ("⏸ Работа приостановлена: агент не отвечает, обращения и авто-сделки остановлены.\n\n"
                    if owner.paused else "▶️ Работа возобновлена.\n\n") + await home_text(session, owner, ctx),
               main_menu(owner, is_admin))


@router.callback_query(Cb.filter(F.s == "biz"))
async def business_section(cq: CallbackQuery, callback_data: Cb, session, owner, ctx) -> None:
    from app.business.service import rights_report

    if callback_data.a == "refresh":
        for rec in (await session.scalars(select(BusinessConnectionRecord).where(
                BusinessConnectionRecord.owner_id == owner.id))).all():
            try:
                bc = await cq.bot.get_business_connection(rec.id)
            except Exception:  # noqa: BLE001
                rec.is_enabled = False
                continue
            rights = bc.rights.model_dump(exclude_none=True) if bc.rights else {}
            rights.setdefault("can_reply", bool(getattr(bc, "can_reply", False)))
            rec.rights, rec.is_enabled = rights, bc.is_enabled
    me = await cq.bot.me()
    recs = (await session.scalars(select(BusinessConnectionRecord).where(BusinessConnectionRecord.owner_id == owner.id))).all()
    parts = [CONNECT_GUIDE.format(username=me.username), ""]
    if not recs:
        parts.append("Подключений пока нет.")
    for rec in recs:
        parts.append(f"<b>Подключение</b> {'🟢 активно' if rec.is_enabled else '🔴 отключено'}\n{rights_report(rec.rights or {})}")
    await show(cq, "\n".join(parts), kb([btn("🔄 Обновить права", "biz", "refresh")]))
