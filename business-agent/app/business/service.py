"""Обработка Telegram Business: подключения, входящие сообщения, ответы агента, «сутпасмотри»."""
from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
from datetime import timedelta
from html import escape
from typing import Any

from aiogram.exceptions import TelegramAPIError
from aiogram.types import BusinessConnection, Message
from sqlalchemy import select, update

from app.ai.agent import AgentResult, DialogueAgent
from app.ai.instructions import get_active_config
from app.ai.llm import LLMError, LLMNotConfigured
from app.ai.prompts import build_dialogue_content, build_dialogue_system
from app.ai.state import DealState
from app.ai.validation import detect_opt_out
from app.bot.ui import btn, deal_actions, deal_card, kb
from app.business.repo import (
    add_message,
    get_or_create_contact,
    get_or_create_conversation,
    primary_template,
    recent_messages,
    trim_history,
)
from app.business.sender import BusinessSender
from app.context import AppContext
from app.core.audit import audit
from app.core.owners import get_or_create_owner, get_policy
from app.db.models import (
    BusinessConnectionRecord,
    Contact,
    Conversation,
    ConversationMessage,
    ConversationMode,
    Deal,
    DealStatus,
    MediaItem,
    OutreachStatus,
    OutreachTask,
    Owner,
    utcnow,
)
from app.media.analyzer import detect_media
from app.nft.pages import find_gift_links
from app.nft.valuation import attributes_from_page, valuate
from app.trading.guard import TradeBlocked, allowed_usernames, get_active_trade_bot

logger = logging.getLogger(__name__)

REQUIRED_RIGHTS = {"can_reply": "отвечать на сообщения", "can_read_messages": "читать сообщения"}
OPTIONAL_RIGHTS = {
    "can_delete_all_messages": "удалять сообщения (нужно, чтобы удалять команду «сутпасмотри»)",
    "can_view_gifts_and_stars": "видеть подарки и звёзды (для работы с подарками)",
}


def rights_report(rights: dict[str, Any]) -> str:
    lines = []
    for key, title in {**REQUIRED_RIGHTS, **OPTIONAL_RIGHTS}.items():
        mark = "✅" if rights.get(key) else ("❌" if key in REQUIRED_RIGHTS else "➖")
        lines.append(f"{mark} {title}")
    return "\n".join(lines)


class BusinessService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.sender = BusinessSender(ctx.bot)
        self._pending: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._llm_warned: set[int] = set()

    # ── уведомления владельцу ─────────────────────────────────────────────

    async def notify(self, telegram_id: int, text: str, reply_markup=None) -> None:
        try:
            await self.ctx.bot.send_message(telegram_id, text, reply_markup=reply_markup)
        except TelegramAPIError as exc:
            logger.warning("Не удалось уведомить %s: %s", telegram_id, exc)

    # ── подключения ───────────────────────────────────────────────────────

    async def on_connection(self, bc: BusinessConnection) -> None:
        allowed = self.ctx.settings.can_use_panel(bc.user.id)
        rights = bc.rights.model_dump(exclude_none=True) if bc.rights else {}
        rights.setdefault("can_reply", bool(getattr(bc, "can_reply", False)))
        async with self.ctx.sessions() as s:
            owner = await get_or_create_owner(s, bc.user.id, bc.user.first_name, bc.user.username) if allowed else None
            rec = await s.get(BusinessConnectionRecord, bc.id)
            if rec is None:
                rec = BusinessConnectionRecord(id=bc.id, user_telegram_id=bc.user.id, user_chat_id=bc.user_chat_id)
                s.add(rec)
            rec.owner_id = owner.id if owner else None
            rec.user_chat_id = bc.user_chat_id
            rec.is_enabled = bc.is_enabled
            rec.allowed = allowed
            rec.rights = rights
            await audit(s, "business_connection", "ok" if allowed else "blocked", owner_id=owner.id if owner else None,
                        actor="system", enabled=bc.is_enabled, rights=rights,
                        error=None if allowed else "пользователь не в списке допуска")
            await s.commit()
        if not allowed:
            await self.notify(bc.user_chat_id, "Бизнес-аккаунт подключён, но доступ к агенту вам не выдан. "
                                               "Обратитесь к администратору.")
            return
        if not bc.is_enabled:
            await self.notify(bc.user_chat_id, "🔌 Бизнес-подключение отключено. Агент больше не видит и не отправляет сообщения.")
            return
        missing = [t for k, t in REQUIRED_RIGHTS.items() if not rights.get(k)]
        text = "🔗 <b>Бизнес-аккаунт подключён</b>\n\nПрава бота:\n" + rights_report(rights)
        if missing:
            text += "\n\n⚠️ Без обязательных прав агент не сможет работать. Включите их в Telegram → Настройки → Telegram для бизнеса → Чат-боты."
        await self.notify(bc.user_chat_id, text, kb([btn("🤖 Настроить агента", "agent")]))

    async def _connection(self, s, connection_id: str) -> BusinessConnectionRecord | None:
        rec = await s.get(BusinessConnectionRecord, connection_id)
        if rec is not None:
            return rec
        try:
            bc = await self.ctx.bot.get_business_connection(connection_id)
        except TelegramAPIError as exc:
            logger.warning("get_business_connection %s: %s", connection_id, exc)
            return None
        await self.on_connection(bc)
        return await s.get(BusinessConnectionRecord, connection_id, populate_existing=True)

    # ── входящие сообщения ────────────────────────────────────────────────

    async def on_message(self, message: Message) -> None:
        if not message.business_connection_id or message.chat.type != "private":
            return
        if message.sender_business_bot is not None:
            return  # исходящее, отправленное ботом (в т.ч. нами) — уже записано при отправке
        schedule_conv: int | None = None
        async with self.ctx.sessions() as s:
            rec = await self._connection(s, message.business_connection_id)
            if rec is None or not rec.is_enabled or not rec.allowed or rec.owner_id is None:
                return
            owner = await s.get(Owner, rec.owner_id)
            chat = message.chat
            contact = await get_or_create_contact(s, owner.id, chat.id, chat.username,
                                                  " ".join(filter(None, [chat.first_name, chat.last_name])) or None)
            conv, _ = await get_or_create_conversation(s, owner, rec, chat.id, contact)
            from_owner = message.from_user is not None and message.from_user.id == rec.user_telegram_id
            text = message.text or message.caption or ""

            if from_owner:
                if text.strip().casefold() == owner.takeover_command.casefold():
                    await self._takeover(s, owner, rec, conv, message)
                    await s.commit()
                    return
                await add_message(s, owner, conv, "owner", text, message.message_id, self._media_stub(message))
                conv.last_owner_message_at = utcnow()
                self._cancel_pending(conv.id)
                await s.commit()
                return

            media_ref = detect_media(message)
            msg = await add_message(s, owner, conv, "contact", text, message.message_id,
                                    {"kind": media_ref.kind, "ok": False, "error": "анализ выполняется"} if media_ref else None)
            conv.last_inbound_at = utcnow()
            if contact.last_contacted_at:
                contact.has_replied = True
            if detect_opt_out(text) and not contact.opted_out:
                await self._mark_opt_out(s, owner, contact, conv)
            await s.commit()
            msg_id, conv_id = msg.id, conv.id

        if media_ref:
            await self._analyze_media(conv_id, msg_id, media_ref, text)
        async with self.ctx.sessions() as s:
            conv = await s.get(Conversation, conv_id)
            owner = await s.get(Owner, conv.owner_id)
            rec = await s.get(BusinessConnectionRecord, conv.business_connection_id)
            reason = self._why_not_reply(owner, conv, rec, conv.contact, message_time=message.date)
            if reason is None:
                schedule_conv = conv_id
            elif reason == "llm":
                await self._warn_llm(owner)
        if schedule_conv:
            self.schedule_reply(schedule_conv)

    async def on_edited(self, message: Message) -> None:
        if not message.business_connection_id:
            return
        async with self.ctx.sessions() as s:
            await s.execute(
                update(ConversationMessage)
                .where(ConversationMessage.telegram_message_id == message.message_id,
                       ConversationMessage.conversation_id.in_(
                           select(Conversation.id).where(Conversation.business_connection_id == message.business_connection_id,
                                                         Conversation.chat_id == message.chat.id)))
                .values(text=(message.text or message.caption or "") + " (изменено)")
            )
            await s.commit()

    async def on_deleted(self, connection_id: str, chat_id: int, message_ids: list[int]) -> None:
        async with self.ctx.sessions() as s:
            await s.execute(
                update(ConversationMessage)
                .where(ConversationMessage.telegram_message_id.in_(message_ids),
                       ConversationMessage.conversation_id.in_(
                           select(Conversation.id).where(Conversation.business_connection_id == connection_id,
                                                         Conversation.chat_id == chat_id)))
                .values(deleted=True)
            )
            await s.commit()

    @staticmethod
    def _media_stub(message: Message) -> dict | None:
        ref = detect_media(message)
        return {"kind": ref.kind, "file_id": ref.file_id, "ok": False, "error": "медиа владельца не анализируется"} if ref else None

    async def _analyze_media(self, conv_id: int, msg_id: int, ref, caption: str) -> None:
        async with self.ctx.sessions() as s:
            conv = await s.get(Conversation, conv_id)
            owner = await s.get(Owner, conv.owner_id)
            state = DealState.load(conv.state)
            refs = (await s.scalars(select(MediaItem).where(MediaItem.owner_id == owner.id, MediaItem.purpose == "reference")
                                    .limit(10))).all()
            references = [{"reference_id": r.id, "description": r.description or (r.analysis or {}).get("summary")} for r in refs]
            discussed = {"description": state.item_description, "attributes": state.item_attributes} if (
                state.item_description or state.item_attributes) else None
            store_dir = self.ctx.settings.media_dir / str(owner.id) if owner.store_media_files else None
        result = await self.ctx.media.analyze(ref, caption=caption, discussed_item=discussed, references=references,
                                              store_dir=store_dir)
        async with self.ctx.sessions() as s:
            msg = await s.get(ConversationMessage, msg_id)
            if msg is not None:
                msg.media = result.to_dict()
            await audit(s, "media_analyzed", "ok" if result.ok else "error", owner_id=owner.id, conversation_id=conv_id,
                        kind=ref.kind, error=result.error)
            await s.commit()

    def _why_not_reply(self, owner: Owner, conv: Conversation, rec: BusinessConnectionRecord | None,
                       contact: Contact, message_time=None) -> str | None:
        if not owner.agent_enabled:
            return "агент выключен"
        if owner.paused:
            return "работа приостановлена"
        if conv.mode != ConversationMode.AUTO:
            return f"диалог в режиме {conv.mode}"
        if rec is None or not rec.is_enabled or not rec.right("can_reply"):
            return "нет права отвечать"
        if contact.opted_out and contact.opted_out_at and message_time and contact.opted_out_at < message_time - timedelta(seconds=5):
            return "собеседник отказался от общения"
        if conv.last_owner_message_at and utcnow() - conv.last_owner_message_at < timedelta(minutes=owner.owner_pause_minutes):
            return "владелец недавно писал вручную"
        if self.ctx.llm is None:
            return "llm"
        return None

    async def _warn_llm(self, owner: Owner) -> None:
        if owner.id in self._llm_warned:
            return
        self._llm_warned.add(owner.id)
        await self.notify(owner.telegram_id, "⚠️ ИИ не настроен: задайте ANTHROPIC_API_KEY в .env. Агент не отвечает собеседникам.")

    async def _mark_opt_out(self, s, owner: Owner, contact: Contact, conv: Conversation | None) -> None:
        contact.opted_out = True
        contact.opted_out_at = utcnow()
        await s.execute(update(OutreachTask).where(
            OutreachTask.contact_id == contact.id,
            OutreachTask.status.in_([OutreachStatus.PENDING_APPROVAL, OutreachStatus.APPROVED, OutreachStatus.MANUAL_REQUIRED]),
        ).values(status=OutreachStatus.CANCELLED, error="собеседник отказался от общения"))
        await audit(s, "contact_opt_out", owner_id=owner.id, conversation_id=conv.id if conv else None, contact_id=contact.id)

    # ── «сутпасмотри» ─────────────────────────────────────────────────────

    async def _takeover(self, s, owner: Owner, rec: BusinessConnectionRecord, conv: Conversation, message: Message) -> None:
        self._cancel_pending(conv.id)
        conv.mode = ConversationMode.MANUAL
        conv.mode_reason = f"команда «{owner.takeover_command}»"
        conv.last_owner_message_at = utcnow()
        deleted_note = "команда удалена из чата"
        if rec.right("can_delete_all_messages"):
            res = await self.sender.delete(rec.id, [message.message_id])
            if not res.ok:
                deleted_note = f"не удалось удалить команду: {res.error}"
        else:
            deleted_note = "команду не удалить: у бота нет права «удалять все сообщения» — удалите её вручную"
        await audit(s, "takeover_manual", owner_id=owner.id, actor="user", conversation_id=conv.id, note=deleted_note)
        await self.notify(
            owner.telegram_id,
            f"🙋 Диалог с {escape(conv.contact.display_name or str(conv.chat_id))} переведён в ручной режим.\n"
            f"Агент не будет писать и создавать сделки в этом чате.\n<i>{escape(deleted_note)}</i>",
            kb([btn("▶️ Вернуть авто-режим", "agent", "auto", conv.id)]),
        )

    async def set_mode(self, conv_id: int, owner_telegram_id: int, mode: ConversationMode) -> bool:
        async with self.ctx.sessions() as s:
            conv = await s.get(Conversation, conv_id)
            owner = await s.get(Owner, conv.owner_id) if conv else None
            if conv is None or owner is None or owner.telegram_id != owner_telegram_id:
                return False
            conv.mode = mode
            conv.mode_reason = "панель"
            if mode == ConversationMode.AUTO:
                state = DealState.load(conv.state)
                state.requires_human_review = False
                state.human_review_reason = None
                conv.state = state.dump()
            else:
                self._cancel_pending(conv.id)
            await audit(s, "conversation_mode", owner_id=owner.id, actor="user", conversation_id=conv.id, mode=str(mode))
            await s.commit()
        return True

    # ── ответы агента ─────────────────────────────────────────────────────

    def _cancel_pending(self, conv_id: int) -> None:
        task = self._pending.pop(conv_id, None)
        if task is not None and not task.done():
            task.cancel()

    def schedule_reply(self, conv_id: int, delay: float | None = None) -> None:
        """Небольшая пауза собирает несколько подряд идущих сообщений в один ответ."""
        self._cancel_pending(conv_id)
        delay = self.ctx.settings.reply_delay_seconds if delay is None else delay

        async def _run() -> None:
            await asyncio.sleep(delay)
            self._pending.pop(conv_id, None)  # дальше задачу не отменяем: идёт обработка
            try:
                await self.run_agent(conv_id)
            except Exception:  # noqa: BLE001
                logger.exception("Ошибка агента в диалоге %s", conv_id)

        self._pending[conv_id] = asyncio.create_task(_run())

    async def _market_context(self, s, owner_id: int, texts: list[str]) -> str | None:
        links = []
        for t in texts:
            links.extend(find_gift_links(t))
        if not links:
            return None
        parts = []
        for slug, number in links[-3:]:
            try:
                page = await self.ctx.gifts.get(slug, number)
            except ConnectionError as exc:
                parts.append(f"{slug}-{number}: страница недоступна ({exc})")
                continue
            if page is None:
                parts.append(f"{slug}-{number}: такого подарка нет")
                continue
            val = await valuate(s, owner_id, slug, attributes_from_page(page))
            parts.append(f"{slug}-{number} (данные t.me/nft):\n{val.render()}")
        return "\n\n".join(parts)

    async def run_agent(self, conv_id: int) -> AgentResult | None:
        async with self._locks[conv_id]:
            async with self.ctx.sessions() as s:
                conv = await s.get(Conversation, conv_id)
                owner = await s.get(Owner, conv.owner_id)
                rec = await s.get(BusinessConnectionRecord, conv.business_connection_id)
                contact = conv.contact
                if self._why_not_reply(owner, conv, rec, contact, message_time=conv.last_inbound_at):
                    return None
                history = await recent_messages(s, conv.id)
                if not history or history[-1].sender != "contact":
                    return None  # отвечать не на что
                last_seen_id = history[-1].id
                latest = []
                for m in reversed(history):
                    if m.sender != "contact":
                        break
                    latest.append(m.text)
                latest_text = "\n".join(reversed(latest))
                state = DealState.load(conv.state)
                cfg = await get_active_config(s)
                bot_cfg = await get_active_trade_bot(s, owner.id)
                allowed = await allowed_usernames(s, owner.id)
                policy = await get_policy(s, owner.id)
                moods = sorted(set((await s.scalars(select(MediaItem.mood).where(
                    MediaItem.owner_id == owner.id, MediaItem.purpose == "send", MediaItem.mood != "none"))).all()))
                transcript = [{"sender": m.sender, "text": m.text, "media": m.media, "at": m.created_at.isoformat()}
                              for m in history]
                texts = [m.text for m in history if m.text] + [
                    (m.media or {}).get("summary") or "" for m in history if m.media]
                market = await self._market_context(s, owner.id, [m.text for m in history if m.sender == "contact"])
                template = None
                if not conv.initial_message_sent and not any(m.sender in ("agent", "owner") for m in history):
                    template = await primary_template(s, owner.id)
                content = build_dialogue_content(
                    transcript=transcript, state=state.dump(),
                    trade_bot={"username": "@" + bot_cfg.bot_username, "currencies": bot_cfg.currencies,
                               "type": bot_cfg.adapter} if bot_cfg and bot_cfg.verified_at else None,
                    limits={"max_deal_amount": policy.max_deal_amount, "auto_max_price": policy.auto_max_price,
                            "currencies": bot_cfg.currencies if bot_cfg else []},
                    contact_profile=contact.profile or {}, sticker_moods=moods, market_context=market,
                    is_new_conversation=template is not None,
                )
                if template is not None:
                    content.append({"type": "text", "text": "<initial_template>\n" + template.text +
                                    "\n</initial_template>\nСобеседник написал первым. Используй шаблон владельца как основу "
                                    "первого ответа, отвечая на его сообщение; не добавляй фактов, которых нет в шаблоне."})
                system = build_dialogue_system(cfg, owner.style_notes, owner.language)
                deal = await s.get(Deal, state.deal_id) if state.deal_id else None
                deal_created = bool(deal and deal.status in (DealStatus.CREATED, DealStatus.USER_ACTION_REQUIRED,
                                                              DealStatus.PAID, DealStatus.COMPLETED))
                deal_paid = bool(deal and deal.status in (DealStatus.PAID, DealStatus.COMPLETED))
                effort = owner.ai_effort

            agent = DialogueAgent(self.ctx.llm)
            try:
                result = await agent.decide(system=system, content=content, state=state, transcript_texts=texts,
                                            latest_contact_text=latest_text, allowed_bot_usernames=allowed,
                                            deal_created=deal_created, deal_paid=deal_paid, effort=effort)
            except LLMNotConfigured:
                await self._warn_llm(owner)
                return None
            except LLMError as exc:
                async with self.ctx.sessions() as s:
                    await audit(s, "agent_reply", "error", owner_id=owner.id, conversation_id=conv_id, error=str(exc))
                    await s.commit()
                await self.notify(owner.telegram_id, f"⚠️ ИИ не ответил в диалоге с {escape(contact.display_name or '')}: {escape(str(exc))}")
                return None

            return await self._apply_result(conv_id, last_seen_id, result, template_id=template.id if template else None)

    async def _apply_result(self, conv_id: int, last_seen_id: int, result: AgentResult, template_id: int | None) -> AgentResult | None:
        async with self.ctx.sessions() as s:
            conv = await s.get(Conversation, conv_id)
            owner = await s.get(Owner, conv.owner_id)
            rec = await s.get(BusinessConnectionRecord, conv.business_connection_id)
            contact = conv.contact
            newest = await s.scalar(select(ConversationMessage.id).where(
                ConversationMessage.conversation_id == conv_id, ConversationMessage.sender == "contact")
                .order_by(ConversationMessage.id.desc()))
            # Пока думал ИИ: владелец перехватил диалог / написал сам / пришли новые сообщения.
            if conv.mode != ConversationMode.AUTO or (conv.last_owner_message_at and conv.last_owner_message_at > utcnow() - timedelta(minutes=owner.owner_pause_minutes)):
                await audit(s, "agent_reply", "skipped", owner_id=owner.id, conversation_id=conv_id, reason="диалог перехвачен")
                await s.commit()
                return None
            if newest != last_seen_id:
                await s.commit()
                self.schedule_reply(conv_id, delay=0.5)
                return None

            conv.state = result.state.dump()
            if result.opt_out and not contact.opted_out:
                await self._mark_opt_out(s, owner, contact, conv)

            sent_ok = None
            if result.reply_text:
                res = await self.sender.send_text(rec.id, conv.chat_id, result.reply_text)
                sent_ok = res.ok
                if res.ok:
                    await add_message(s, owner, conv, "agent", result.reply_text, res.message_id)
                    conv.last_outbound_at = utcnow()
                    if template_id:
                        conv.initial_message_sent = True
                else:
                    await self.notify(owner.telegram_id, f"⚠️ Не удалось отправить ответ ({escape(res.kind or '')}): "
                                                         f"{escape(res.error or '')}")
                await audit(s, "agent_reply", "ok" if res.ok else "error", owner_id=owner.id, conversation_id=conv_id,
                            error=res.error, intent=result.intent, rejected_updates=result.rejected_updates)
            if result.sticker_mood != "none" and sent_ok is not False:
                items = (await s.scalars(select(MediaItem).where(
                    MediaItem.owner_id == owner.id, MediaItem.purpose == "send", MediaItem.mood == result.sticker_mood))).all()
                if items:
                    item = random.choice(items)
                    res = await self.sender.send_media(rec.id, conv.chat_id, item.kind, item.file_id)
                    if res.ok:
                        await add_message(s, owner, conv, "agent", "", res.message_id,
                                          {"kind": item.kind, "ok": True, "summary": f"отправлен {item.kind} ({item.mood})"})

            if result.handoff:
                conv.mode = ConversationMode.REVIEW
                conv.mode_reason = result.handoff_reason
                await audit(s, "agent_handoff", owner_id=owner.id, conversation_id=conv_id, reason=result.handoff_reason)
                await self.notify(
                    owner.telegram_id,
                    f"🧑‍💼 Нужен человек в диалоге с {escape(contact.display_name or str(conv.chat_id))}.\n"
                    f"Причина: {escape(result.handoff_reason or '—')}",
                    kb([btn("▶️ Вернуть авто-режим", "agent", "auto", conv.id),
                        btn("🙋 Оставить ручной", "agent", "manual", conv.id)]),
                )
            elif result.owner_note:
                await self.notify(owner.telegram_id, f"📝 {escape(contact.display_name or '')}: {escape(result.owner_note)}")

            await trim_history(s, owner, conv_id)
            await s.commit()

            if result.ready_for_deal and not result.handoff and not result.opt_out:
                await self._deal_from_conversation(s, owner, conv)
                await s.commit()
        return result

    async def _deal_from_conversation(self, s, owner: Owner, conv: Conversation) -> None:
        try:
            prepared = await self.ctx.deals.prepare_from_conversation(s, conv, created_by="auto")
        except TradeBlocked as exc:
            await audit(s, "deal_prepared", "blocked", owner_id=owner.id, conversation_id=conv.id, error=exc.message)
            await self.notify(owner.telegram_id, f"⛔️ Сделку подготовить нельзя: {escape(exc.message)}",
                              kb([btn("🛍 Торговый бот", "trade")]))
            return
        if prepared.deal is None:
            return
        deal = prepared.deal
        if not prepared.created_now:
            return
        policy = await get_policy(s, owner.id)
        if policy.auto_mode_enabled and not policy.require_user_confirmation:
            step = await self.ctx.deals.confirm_and_create(s, deal, automatic=True)
            text = f"🤖 Авто-режим: {escape(step.message)}"
            if step.problems:
                text += "\n" + "\n".join(f"• {escape(p)}" for p in step.problems)
            if deal.status == DealStatus.CREATED and deal.side == "buy" and policy.auto_pay_enabled:
                pay = await self.ctx.deals.pay(s, deal, automatic=True)
                text += f"\n💸 {escape(pay.message)}"
                if pay.problems:
                    text += "\n" + "\n".join(f"• {escape(p)}" for p in pay.problems)
            await self.notify(owner.telegram_id, deal_card(deal, conv.contact) + "\n\n" + text, deal_actions(deal))
        else:
            await self.notify(owner.telegram_id, "🤝 Условия согласованы. Проверьте и подтвердите сделку:\n\n"
                              + deal_card(deal, conv.contact), deal_actions(deal))
