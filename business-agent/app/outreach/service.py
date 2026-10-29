"""Первые обращения к найденным контактам.

Ограничение Telegram: бот бизнес-аккаунта может писать только в чаты, где есть недавняя
активность; начать переписку с новым человеком через Bot API нельзя. Поэтому:
- если отправка через бизнес-подключение возможна — отправляем (с лимитами и паузами);
- иначе задача получает статус MANUAL_REQUIRED: владелец получает готовый текст и ссылку
  на профиль и отправляет первое сообщение сам. Дальше диалог ведёт агент.
Никаких обходов ограничений, массовых рассылок и обращений к отказавшимся.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from html import escape

from sqlalchemy import func, select

from app.ai.agent import prepare_initial_message
from app.bot.ui import btn, kb
from app.business.repo import add_message, get_or_create_conversation, owner_connection, primary_template
from app.core.audit import audit
from app.db.models import Contact, OutreachStatus, OutreachTask, Owner, ParserConfig, utcnow
from app.trading.guard import allowed_usernames

logger = logging.getLogger(__name__)


class OutreachService:
    def __init__(self, ctx, business) -> None:
        self.ctx = ctx
        self.business = business  # BusinessService: sender + notify

    async def _sent_today(self, s, owner_id: int) -> int:
        return int(await s.scalar(select(func.count(OutreachTask.id)).where(
            OutreachTask.owner_id == owner_id, OutreachTask.status == OutreachStatus.SENT,
            OutreachTask.sent_at >= utcnow() - timedelta(days=1))) or 0)

    async def _last_sent_at(self, s, owner_id: int):
        return await s.scalar(select(func.max(OutreachTask.sent_at)).where(
            OutreachTask.owner_id == owner_id, OutreachTask.status == OutreachStatus.SENT))

    async def process_owner(self, owner_id: int) -> None:
        """Обрабатывает не более одной одобренной задачи за вызов (паузы между обращениями)."""
        async with self.ctx.sessions() as s:
            owner = await s.get(Owner, owner_id)
            if owner is None or owner.paused or not owner.agent_enabled:
                return
            if await self._sent_today(s, owner.id) >= owner.outreach_daily_limit:
                return
            last = await self._last_sent_at(s, owner.id)
            if last and utcnow() - last < timedelta(seconds=owner.outreach_min_interval_seconds):
                return
            task = await s.scalar(select(OutreachTask).where(
                OutreachTask.owner_id == owner.id, OutreachTask.status == OutreachStatus.APPROVED
            ).order_by(OutreachTask.id))
            if task is None:
                return
            await self.send_task(s, owner, task)
            await s.commit()

    async def send_task(self, s, owner: Owner, task: OutreachTask) -> None:
        contact: Contact = task.contact
        parser = await s.get(ParserConfig, task.parser_id) if task.parser_id else None
        parser_name = parser.name if parser else None
        if contact.opted_out:
            task.status, task.error = OutreachStatus.CANCELLED, "собеседник отказался от общения"
            return
        template = await primary_template(s, owner.id)
        if template is None:
            task.status, task.error = OutreachStatus.PENDING_APPROVAL, "нет включённого начального текста"
            await self.business.notify(owner.telegram_id, "⚠️ Нет включённого шаблона в «💬 Начальный текст» — обращения на паузе.")
            await audit(s, "outreach", "blocked", owner_id=owner.id, parser=parser_name, error=task.error)
            return
        task.template_id = template.id
        task.attempts += 1
        if not task.prepared_text:
            task.prepared_text, adapted = await prepare_initial_message(
                self.ctx.llm, template.text, contact.profile or {}, allow_adaptation=template.allow_adaptation,
                allowed_bot_usernames=await allowed_usernames(s, owner.id),
            )
        rec = await owner_connection(s, owner.id)
        if rec is None or not rec.right("can_reply"):
            return await self._manual(s, owner, task, contact, "бизнес-аккаунт не подключён или нет права отвечать", parser_name)
        if not contact.telegram_user_id:
            return await self._manual(s, owner, task, contact, "у контакта известен только username — Bot API не может начать чат", parser_name)

        res = await self.business.sender.send_text(rec.id, contact.telegram_user_id, task.prepared_text)
        if not res.ok:
            if res.kind in ("chat_unavailable", "no_rights", "forbidden", "bad_request"):
                return await self._manual(s, owner, task, contact, f"Telegram не дал написать первым: {res.error}", parser_name)
            task.status, task.error = OutreachStatus.FAILED, res.error
            await audit(s, "outreach", "error", owner_id=owner.id, parser=parser_name, error=res.error, contact_id=contact.id)
            return
        conv, _ = await get_or_create_conversation(s, owner, rec, contact.telegram_user_id, contact)
        conv.initial_message_sent = True
        conv.last_outbound_at = utcnow()
        await add_message(s, owner, conv, "agent", task.prepared_text, res.message_id)
        task.status, task.sent_message_id, task.sent_at = OutreachStatus.SENT, res.message_id, utcnow()
        contact.first_contacted_at = contact.first_contacted_at or utcnow()
        contact.last_contacted_at = utcnow()
        contact.contact_attempts += 1
        await audit(s, "outreach", "ok", owner_id=owner.id, parser=parser_name, conversation_id=conv.id,
                    contact_id=contact.id, message_id=res.message_id)

    async def _manual(self, s, owner: Owner, task: OutreachTask, contact: Contact, reason: str, parser_name: str | None) -> None:
        task.status, task.error = OutreachStatus.MANUAL_REQUIRED, reason
        contact.last_contacted_at = utcnow()  # чтобы не предлагать повторно до истечения паузы
        link = f"https://t.me/{contact.username}" if contact.username else f"tg://user?id={contact.telegram_user_id}"
        await audit(s, "outreach", "skipped", owner_id=owner.id, parser=parser_name, error=reason, contact_id=contact.id)
        await self.business.notify(
            owner.telegram_id,
            f"✉️ <b>Первое сообщение нужно отправить вручную</b>\n{escape(reason)}\n\n"
            f"Контакт: {escape(contact.display_name or '')} {escape(link)}\n\n"
            f"Текст (скопируйте):\n<code>{escape(task.prepared_text or '')}</code>\n\n"
            "Когда собеседник ответит, агент продолжит диалог сам.",
            kb([btn("✔️ Отправил", "parsers", "out_done", task.id), btn("✖️ Пропустить", "parsers", "out_cancel", task.id)],
               back=None),
        )
