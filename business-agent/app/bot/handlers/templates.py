from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select, update

from app.ai.agent import prepare_initial_message
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.inputs import ask, input_field
from app.bot.ui import btn, kb, onoff
from app.core.audit import audit
from app.db.models import InitialTemplate
from app.trading.guard import allowed_usernames

router = Router(name="templates")


@input_field("tpl_new", "Отправьте текст первого сообщения. Агент будет использовать его как основу.", "tpl")
async def tpl_new(session, owner, text, **_):
    if len(text) > 3500:
        return False, "Слишком длинно (макс. 3500 символов)"
    has_primary = await session.scalar(select(InitialTemplate.id).where(
        InitialTemplate.owner_id == owner.id, InitialTemplate.is_primary.is_(True)))
    count = len((await session.scalars(select(InitialTemplate.id).where(InitialTemplate.owner_id == owner.id))).all())
    session.add(InitialTemplate(owner_id=owner.id, text=text, title=f"Вариант {count + 1}", is_primary=not has_primary))
    await audit(session, "template_added", owner_id=owner.id, actor="user")
    return True, "Шаблон сохранён."


@input_field("tpl_edit", "Отправьте новый текст шаблона.", "tpl:view")
async def tpl_edit(session, owner, text, data, **_):
    tpl = await session.get(InitialTemplate, int(data["obj_id"]))
    if tpl is None or tpl.owner_id != owner.id:
        return False, "Шаблон не найден"
    tpl.text = text
    await audit(session, "template_edited", owner_id=owner.id, actor="user", template_id=tpl.id)
    return True, "Шаблон обновлён."


async def _get(session, owner, tpl_id):
    tpl = await session.get(InitialTemplate, tpl_id)
    return tpl if tpl and tpl.owner_id == owner.id else None


@router.callback_query(Cb.filter(F.s == "tpl"))
async def templates(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner, ctx):
    a, i = callback_data.a, callback_data.i
    if a == "add":
        return await ask(cq, state, "tpl_new")
    if a != "show":
        tpl = await _get(session, owner, i)
        if tpl is None:
            return await cq.answer("Шаблон не найден", show_alert=True)
        if a == "edit":
            return await ask(cq, state, "tpl_edit", escape(tpl.text), obj_id=tpl.id)
        if a == "toggle":
            tpl.is_enabled = not tpl.is_enabled
        elif a == "adapt":
            tpl.allow_adaptation = not tpl.allow_adaptation
        elif a == "primary":
            await session.execute(update(InitialTemplate).where(InitialTemplate.owner_id == owner.id).values(is_primary=False))
            tpl.is_primary = True
        elif a == "delete":
            await session.delete(tpl)
            await audit(session, "template_deleted", owner_id=owner.id, actor="user", template_id=tpl.id)
            a = "show"
        elif a == "test":
            text, adapted = await prepare_initial_message(
                ctx.llm, tpl.text, {"name": owner.first_name} if owner.first_name else {},
                allow_adaptation=tpl.allow_adaptation, allowed_bot_usernames=await allowed_usernames(session, owner.id))
            await cq.message.answer("🧪 <b>Тестовое сообщение (отправлено только вам):</b>\n\n" + escape(text)
                                    + ("\n\n<i>адаптировано ИИ по профилю</i>" if adapted else ""))
            return await cq.answer()
        if a != "show":
            await session.flush()
            return await show(cq, *_view(tpl))
    tpls = (await session.scalars(select(InitialTemplate).where(InitialTemplate.owner_id == owner.id)
                                  .order_by(InitialTemplate.id))).all()
    lines = ["<b>💬 Начальный текст</b>",
             "Используется для первого обращения к найденным контактам и как основа первого ответа, "
             "если собеседник написал первым. Продолжение диалога ведётся по истории переписки."]
    rows = [[btn("➕ Добавить текст", "tpl", "add")]]
    for t in tpls:
        mark = "⭐️ " if t.is_primary else ""
        lines.append(f"\n{mark}<b>{escape(t.title)}</b> {onoff(t.is_enabled)}\n{escape(t.text[:200])}")
        rows.append([btn(f"{mark}{t.title}", "tpl", "view", t.id)])
    await show(cq, "\n".join(lines), kb(*rows))


def _view(tpl: InitialTemplate):
    text = (f"<b>{escape(tpl.title)}</b>{' ⭐️ основной' if tpl.is_primary else ''}\n"
            f"Статус: {onoff(tpl.is_enabled)}\nАдаптация под контакт: {onoff(tpl.allow_adaptation)} "
            "(только по данным из источника)\n\n" + escape(tpl.text))
    return text, kb(
        [btn("✏️ Изменить", "tpl", "edit", tpl.id), btn("🧪 Тест себе", "tpl", "test", tpl.id)],
        [btn("⏯ Вкл/выкл", "tpl", "toggle", tpl.id), btn("🎯 Адаптация", "tpl", "adapt", tpl.id)],
        [btn("⭐️ Сделать основным", "tpl", "primary", tpl.id), btn("🗑 Удалить", "tpl", "delete", tpl.id)],
        back="tpl",
    )

