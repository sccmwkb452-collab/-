"""Администрирование глобальных инструкций ИИ. Доступ — только по Telegram ID из ADMIN_IDS."""
import json
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.ai.instructions import (
    AdminInput,
    NotAdminError,
    analyze_instruction,
    apply_pending,
    get_active_config,
    list_versions,
    reject_pending,
    rollback_to,
)
from app.ai.llm import LLMError
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.states import AdminInput as AdminState
from app.bot.ui import btn, kb
from app.db.models import AdminMaterial, PendingInstruction
from app.media.analyzer import detect_media

router = Router(name="admin")


def _pending_text(p: PendingInstruction) -> str:
    an = p.analysis
    parts = [f"<b>Предложение #{p.id}</b> · тип: {escape(an.get('instruction_type', '?'))}",
             f"Кратко: {escape(an.get('summary', ''))}"]
    for title, key in (("➕ Новые правила", "new_rules"), ("➖ Удаляемые правила", "removed_rules")):
        if an.get(key):
            parts.append(f"\n<b>{title}:</b>\n" + "\n".join(f"• {escape(r)}" for r in an[key]))
    if an.get("conflicts"):
        parts.append("\n<b>⚠️ Конфликты:</b>\n" + "\n".join(
            f"• было: {escape(c['existing'])}\n  стало: {escape(c['new'])}\n  {escape(c['explanation'])}" for c in an["conflicts"]))
    concerns = (an.get("safety_concerns") or []) + (an.get("code_checks") or [])
    if concerns:
        parts.append("\n<b>🛡 Не будет применено / замечания безопасности:</b>\n" + "\n".join(f"• {escape(c)}" for c in concerns))
    parts.append("\nНеизменяемые правила безопасности всегда стоят выше инструкций администратора.")
    return "\n".join(parts)[:4000]


@router.callback_query(Cb.filter(F.s == "admin"))
async def admin(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner, ctx, is_admin):
    if not is_admin:
        return await cq.answer("Только для администратора", show_alert=True)
    a, i = callback_data.a, callback_data.i
    try:
        if a == "new":
            await state.set_state(AdminState.collecting)
            await state.update_data(texts=[], material_ids=[])
            await cq.message.answer("Отправьте инструкции: текст, промпты, скриншоты, фото, видео, GIF, стикеры, примеры "
                                    "переписок, правила торговли. Можно несколькими сообщениями. Затем нажмите «Анализировать».",
                                    reply_markup=kb([btn("🧠 Анализировать", "admin", "analyze")], back="admin"))
            return await cq.answer()
        if a == "analyze":
            data = await state.get_data()
            await state.clear()
            if not data.get("texts") and not data.get("material_ids"):
                return await cq.answer("Нет материалов", show_alert=True)
            if ctx.llm is None:
                return await cq.answer("ИИ не настроен (ANTHROPIC_API_KEY)", show_alert=True)
            await cq.answer("Анализирую…")
            materials = list((await session.scalars(select(AdminMaterial).where(
                AdminMaterial.id.in_(data.get("material_ids") or [])))).all())
            try:
                pending = await analyze_instruction(session, ctx.llm, ctx.settings, cq.from_user.id,
                                                    AdminInput("\n\n".join(data.get("texts") or []), materials))
            except LLMError as exc:
                await cq.message.answer(f"⚠️ Анализ не удался: {escape(str(exc))}")
                return
            await cq.message.answer(_pending_text(pending), reply_markup=kb(
                [btn("✅ Применить", "admin", "apply", pending.id), btn("✖️ Отклонить", "admin", "reject", pending.id)],
                [btn("📄 Итоговая конфигурация", "admin", "proposed", pending.id)], back="admin"))
            return
        if a == "proposed":
            p = await session.get(PendingInstruction, i)
            body = json.dumps((p.analysis or {}).get("proposed", {}), ensure_ascii=False, indent=1) if p else "—"
            await cq.message.answer(f"<pre>{escape(body[:3900])}</pre>")
            return await cq.answer()
        if a == "apply":
            cfg = await apply_pending(session, ctx.settings, cq.from_user.id, i)
            return await show(cq, f"✅ Применена версия {cfg.version}. Действует для всех последующих ответов.", kb(back="admin"))
        if a == "reject":
            await reject_pending(session, ctx.settings, cq.from_user.id, i)
            return await show(cq, "Предложение отклонено.", kb(back="admin"))
        if a == "versions":
            versions = await list_versions(session)
            lines = ["<b>📚 Версии конфигурации</b>"]
            rows = []
            for v in versions:
                lines.append(f"{'⭐️' if v.is_active else '•'} v{v.version} {v.created_at:%d.%m.%Y %H:%M} — {escape(v.note[:80])}")
                if not v.is_active:
                    rows.append([btn(f"↩️ Откатить к v{v.version}", "admin", "rollback", v.version)])
            return await show(cq, "\n".join(lines), kb(*rows, back="admin"))
        if a == "rollback":
            cfg = await rollback_to(session, ctx.settings, cq.from_user.id, i)
            return await show(cq, f"↩️ Откат выполнен: активна версия {cfg.version} (копия v{i}).", kb(back="admin"))
    except (NotAdminError, ValueError) as exc:
        return await cq.answer(str(exc), show_alert=True)

    cfg = await get_active_config(session)
    text = ("<b>🛡 Администратор: глобальные инструкции ИИ</b>\n"
            f"Активная версия: {cfg.version if cfg else 'нет'}\n"
            + (f"Описание: {escape(cfg.note[:300])}\n" if cfg else "")
            + "\nНовые инструкции анализируются ИИ: выделяются правила, ищутся конфликты, затем вы подтверждаете "
              "применение. История версий хранится, откат — в один клик.")
    await show(cq, text, kb([btn("✍️ Новая инструкция", "admin", "new"), btn("📚 Версии", "admin", "versions")]))


@router.message(AdminState.collecting)
async def collect(message: Message, state: FSMContext, session, ctx, is_admin):
    if not is_admin:
        await state.clear()
        return
    data = await state.get_data()
    texts, material_ids = list(data.get("texts") or []), list(data.get("material_ids") or [])
    ref = detect_media(message)
    caption = message.text or message.caption or ""
    if ref is None and message.document is not None and (message.document.mime_type or "").startswith("text/"):
        raw = (await message.bot.download(message.document.file_id)).getvalue()[:100_000]
        caption = (caption + "\n" + raw.decode("utf-8", errors="replace")).strip()
    if ref is not None:
        analysis = await ctx.media.analyze(ref, caption=caption)
        mat = AdminMaterial(admin_telegram_id=message.from_user.id, kind=ref.kind, file_id=ref.file_id,
                            file_unique_id=ref.file_unique_id, text=caption, stored_path=analysis.stored_path,
                            analysis={"ok": analysis.ok, "summary": analysis.summary, "error": analysis.error,
                                      **analysis.details})
        session.add(mat)
        await session.flush()
        material_ids.append(mat.id)
        note = (f"медиа проанализировано: {escape(analysis.summary or '')}" if analysis.ok
                else f"⚠️ медиа не проанализировано: {escape(analysis.error or '')}")
    elif caption:
        texts.append(caption)
        note = "текст принят"
    else:
        await message.answer("Этот тип сообщения не поддерживается.")
        return
    await state.update_data(texts=texts, material_ids=material_ids)
    await message.answer(f"Принято ({len(texts) + len(material_ids)}): {note}",
                         reply_markup=kb([btn("🧠 Анализировать", "admin", "analyze")], back=None))
