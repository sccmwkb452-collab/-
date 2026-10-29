from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.ai.schemas import STICKER_MOODS
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.states import Input
from app.bot.ui import btn, kb
from app.core.audit import audit
from app.db.models import MediaItem
from app.media.analyzer import detect_media

router = Router(name="media")
MOOD_RU = {"none": "не отправлять", "greeting": "приветствие", "thanks": "благодарность", "agree": "согласие",
           "thinking": "раздумье", "deal_done": "сделка завершена"}


@router.callback_query(Cb.filter(F.s == "media"))
async def media(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner):
    a, i = callback_data.a, callback_data.i
    if a in ("add_send", "add_ref"):
        await state.set_state(Input.media)
        await state.update_data(purpose="send" if a == "add_send" else "reference")
        await cq.message.answer("Отправьте стикер, GIF, фото или видео. Подпись к фото/видео сохранится как описание.\n/cancel — отмена")
        return await cq.answer()
    item = await session.get(MediaItem, i) if i else None
    if item is not None and item.owner_id != owner.id:
        item = None
    if a == "mood" and item:
        idx = STICKER_MOODS.index(item.mood) if item.mood in STICKER_MOODS else 0
        item.mood = STICKER_MOODS[(idx + 1) % len(STICKER_MOODS)]
    elif a == "delete" and item:
        await session.delete(item)
        await session.flush()
        item = None
    elif a == "preview" and item:
        send = {"sticker": cq.message.answer_sticker, "animation": cq.message.answer_animation,
                "photo": cq.message.answer_photo, "video": cq.message.answer_video}[item.kind]
        await send(item.file_id)
        return await cq.answer()
    if item is not None:
        text = (f"<b>{item.kind}</b> · {'для отправки' if item.purpose == 'send' else 'образец для сравнения'}\n"
                f"Когда отправлять: {MOOD_RU.get(item.mood, item.mood)}\n"
                f"Описание: {escape(item.description or '—')}\n"
                f"Анализ: {escape((item.analysis or {}).get('summary') or (item.analysis or {}).get('error') or '—')}")
        return await show(cq, text, kb([btn("👁 Показать", "media", "preview", item.id), btn("🎭 Настроение", "media", "mood", item.id)],
                                       [btn("🗑 Удалить", "media", "delete", item.id)], back="media"))
    items = (await session.scalars(select(MediaItem).where(MediaItem.owner_id == owner.id).order_by(MediaItem.id.desc()).limit(20))).all()
    lines = ["<b>📁 Медиа и материалы</b>",
             "• <b>Для отправки</b> — стикеры/GIF/фото, которые агент может отправить. Агент выбирает только по "
             "настроению диалога, никогда случайно; «не отправлять» — исключить.",
             "• <b>Образцы</b> — фото товаров для сравнения с медиа собеседников."]
    rows = [[btn("➕ Для отправки", "media", "add_send"), btn("➕ Образец", "media", "add_ref")]]
    for it in items:
        label = f"{it.kind} · {MOOD_RU.get(it.mood, it.mood) if it.purpose == 'send' else 'образец'}"
        rows.append([btn(label, "media", "view", it.id)])
    await show(cq, "\n".join(lines), kb(*rows))


@router.message(Input.media, F.text == "/cancel")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=kb(back="media"))


@router.message(Input.media)
async def receive(message: Message, state: FSMContext, session, owner, ctx):
    ref = detect_media(message)
    if ref is None or ref.kind not in ("sticker", "animation", "photo", "video", "image_document"):
        await message.answer("Это не стикер, GIF, фото или видео. Отправьте медиа или /cancel.")
        return
    data = await state.get_data()
    await state.clear()
    kind = "photo" if ref.kind == "image_document" else ref.kind
    store_dir = ctx.settings.media_dir / str(owner.id) / "library" if owner.store_media_files else None
    analysis = await ctx.media.analyze(ref, caption=message.caption, store_dir=store_dir)
    item = MediaItem(owner_id=owner.id, kind=kind, file_id=ref.file_id, file_unique_id=ref.file_unique_id,
                     purpose=data.get("purpose", "send"), mood="none", description=message.caption or "",
                     analysis={"summary": analysis.summary, "error": analysis.error, **analysis.details},
                     stored_path=analysis.stored_path)
    session.add(item)
    await session.flush()
    await audit(session, "media_library_added", owner_id=owner.id, actor="user", kind=kind, ok=analysis.ok, error=analysis.error)
    status = f"Анализ: {escape(analysis.summary)}" if analysis.ok else f"⚠️ Медиа сохранено, но не проанализировано: {escape(analysis.error or '')}"
    await message.answer(f"✅ Добавлено.\n{status}\n\nЗадайте настроение, чтобы агент мог его отправлять.",
                         reply_markup=kb([btn("🎭 Настроение", "media", "mood", item.id)], back="media"))
