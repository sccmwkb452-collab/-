"""Admin: catalog categories."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.states import CategoryEdit
from bot.callbacks import Adm
from bot.ui import Screen, show
from catalog.manage import products_in_category
from database.models import Category
from keyboards import admin as akb
from keyboards.user import btn, rows
from services.audit import log_action
from services.formatting import esc

router = Router(name="admin_categories")

FIELDS = {
    "title": ("Название", 64),
    "emoji": ("Эмодзи", 16),
    "description": ("Описание", 300),
    "sort_order": ("Порядок (число, меньше — выше)", 6),
}


async def categories_screen(session: AsyncSession) -> Screen:
    cats = (await session.execute(select(Category).order_by(Category.sort_order, Category.id))).scalars().all()
    items = [(f"{'👁' if c.is_active else '🙈'} {c.emoji} {c.title} · #{c.sort_order}", Adm(s="cat", id=c.id)) for c in cats]
    text = "🗂 <b>Категории</b>\n\n👁 видна покупателям · 🙈 скрыта.\nЧисло после # — порядок в каталоге."
    return Screen(text, akb.listing(items, 0, 1, None, [[btn("➕ Новая категория", Adm(s="cnew"), style="primary")]]))


@router.callback_query(Adm.filter(F.s == "cats"))
async def categories(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await show(callback, await categories_screen(session))


async def category_screen(session: AsyncSession, c: Category) -> Screen:
    n = await products_in_category(session, c.id)
    text = (
        f"🗂 <b>{esc(c.emoji)} {esc(c.title)}</b> · #{c.id}\n\n"
        f"Статус: {'👁 видна' if c.is_active else '🙈 скрыта'}\n"
        f"Порядок: {c.sort_order}\n"
        f"Товаров: {n}\n\n"
        f"Описание: {esc(c.description or '—')}"
    )
    e = lambda f: Adm(s="ce", id=c.id, v=f)  # noqa: E731
    lines = [
        [btn("✏️ Название", e("title")), btn("😀 Эмодзи", e("emoji"))],
        [btn("📝 Описание", e("description")), btn("🔢 Порядок", e("sort_order"))],
        [btn("🙈 Скрыть" if c.is_active else "👁 Показать", Adm(s="ctog", id=c.id))],
    ]
    if n == 0:
        lines.append([btn("🗑 Удалить", Adm(s="cdel", id=c.id), style="danger")])
    lines.append([akb.back("cats", "◀️ К категориям")])
    return Screen(text, rows(*lines))


@router.callback_query(Adm.filter(F.s == "cat"))
async def category(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext, callback_answer: CallbackAnswer) -> None:
    await state.clear()
    c = await session.get(Category, callback_data.id, populate_existing=True)
    if c is None:
        callback_answer.text = "Категория не найдена"
        await show(callback, await categories_screen(session))
        return
    await show(callback, await category_screen(session, c))


@router.callback_query(Adm.filter(F.s == "cnew"))
async def new_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CategoryEdit.value)
    await state.update_data(cid=0, field="title")
    await show(callback, Screen("➕ Отправьте название новой категории (до 64 символов). Эмодзи можно поставить в начале: <code>🆕 Новинки</code>", akb.cancel("cats")))


@router.callback_query(Adm.filter(F.s == "ce"))
async def edit(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    if callback_data.v not in FIELDS:
        return
    await state.set_state(CategoryEdit.value)
    await state.update_data(cid=callback_data.id, field=callback_data.v)
    name, limit = FIELDS[callback_data.v]
    extra = "\nОтправьте <code>-</code>, чтобы очистить." if callback_data.v == "description" else ""
    await show(callback, Screen(f"✏️ <b>{name}</b>\nОтправьте новое значение (до {limit} символов).{extra}", akb.cancel("cat", id=callback_data.id)))


def _split_emoji(text: str) -> tuple[str, str]:
    first, _, rest = text.partition(" ")
    if rest and not any(ch.isalnum() for ch in first) and len(first) <= 16:
        return first, rest.strip()
    return "📦", text


@router.message(CategoryEdit.value, F.text)
async def edit_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    cid, field = data["cid"], data["field"]
    raw = message.text.strip()
    back = akb.cancel("cat", id=cid) if cid else akb.cancel("cats")
    if cid == 0:  # creating
        emoji, title = _split_emoji(raw)
        if not title or len(title) > 64:
            await message.answer("Название: от 1 до 64 символов.", reply_markup=back)
            return
        c = Category(title=title, emoji=emoji)
        session.add(c)
        await session.flush()
        await log_action(session, message.from_user.id, "category_create", f"category:{c.id}", title)
        await session.commit()
        await state.clear()
        await message.answer("✅ Категория создана")
        await show(message, await category_screen(session, c))
        return

    c = await session.get(Category, cid)
    if c is None:
        await state.clear()
        await message.answer("Категория не найдена.")
        return
    name, limit = FIELDS[field]
    if field == "sort_order":
        if not raw.lstrip("-").isdigit() or abs(int(raw)) > 99999:
            await message.answer("Укажите целое число.", reply_markup=back)
            return
        value: object = int(raw)
    elif field == "description" and raw == "-":
        value = ""
    elif not raw or len(raw) > limit:
        await message.answer(f"Длина: от 1 до {limit} символов.", reply_markup=back)
        return
    else:
        value = raw
    setattr(c, field, value)
    await log_action(session, message.from_user.id, f"category_{field}", f"category:{cid}", str(value)[:200])
    await session.commit()
    await state.clear()
    await message.answer(f"✅ {name}: сохранено")
    await show(message, await category_screen(session, c))


@router.callback_query(Adm.filter(F.s == "ctog"))
async def toggle(callback: CallbackQuery, callback_data: Adm, session: AsyncSession) -> None:
    c = await session.get(Category, callback_data.id)
    if c is None:
        return
    c.is_active = not c.is_active
    await log_action(session, callback.from_user.id, "category_toggle", f"category:{c.id}", str(c.is_active))
    await session.commit()
    await show(callback, await category_screen(session, c))


@router.callback_query(Adm.filter(F.s == "cdel"))
async def delete_confirm(callback: CallbackQuery, callback_data: Adm) -> None:
    await show(callback, Screen("🗑 Удалить категорию без товаров?", akb.confirm(Adm(s="cdelok", id=callback_data.id), Adm(s="cat", id=callback_data.id), "🗑 Удалить")))


@router.callback_query(Adm.filter(F.s == "cdelok"))
async def delete(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, callback_answer: CallbackAnswer) -> None:
    c = await session.get(Category, callback_data.id)
    if c is not None:
        if await products_in_category(session, c.id):
            callback_answer.text, callback_answer.show_alert = "В категории есть товары: перенесите их или скройте категорию", True
            await show(callback, await category_screen(session, c))
            return
        await session.delete(c)
        await log_action(session, callback.from_user.id, "category_delete", f"category:{callback_data.id}", c.title)
        await session.commit()
        callback_answer.text = "Категория удалена"
    await show(callback, await categories_screen(session))
