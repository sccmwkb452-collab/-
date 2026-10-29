import time

import pytest
from aiogram.types import Message
from sqlalchemy import select

from app.business.service import BusinessService
from app.context import AppContext
from app.db.models import BusinessConnectionRecord, Contact, Conversation, ConversationMessage, Deal, DealStatus
from app.deals.manager import DealManager
from app.media.analyzer import MediaAnalyzer
from tests.conftest import OWNER_TG, FakeAdapter, FakeBot, FakeFactory, FakeLLM, add_trade_bot

CONTACT = 555


def msg(text, from_id, mid=1):
    return Message.model_validate({
        "message_id": mid, "date": int(time.time()), "business_connection_id": "conn1",
        "chat": {"id": CONTACT, "type": "private", "first_name": "Seller", "username": "seller1"},
        "from": {"id": from_id, "is_bot": False, "first_name": "X"}, "text": text,
    })


def reply(text="Здравствуйте! Да, интересно.", **over):
    base = {
        "intent": "interest", "interest_level": "medium", "reply_text": text, "send_sticker_mood": "none",
        "state_update": {"conversation_stage": "discovery", "counterparty_role": None, "product_type": None,
                         "item_description": None, "item_attributes": [], "quantity": None, "seller_price": None,
                         "buyer_target_price": None, "agreed_price": None, "currency": None, "payment_method": None,
                         "new_objections": [], "new_agreements": []},
        "opt_out": False, "handoff_required": False, "handoff_reason": None, "ready_for_deal": False, "owner_note": None,
    }
    base.update(over)
    return base


@pytest.fixture
async def env(sessions, owner, settings):
    async with sessions() as s:
        s.add(BusinessConnectionRecord(id="conn1", owner_id=owner.id, user_telegram_id=OWNER_TG, user_chat_id=OWNER_TG,
                                       is_enabled=True, allowed=True,
                                       rights={"can_reply": True, "can_read_messages": True, "can_delete_all_messages": True}))
        await s.commit()
    bot = FakeBot()
    llm = FakeLLM()
    ctx = AppContext(settings=settings, bot=bot, sessions=sessions, llm=llm,
                     media=MediaAnalyzer(llm, downloader=None), trade_adapters=FakeFactory(FakeAdapter()),
                     deals=DealManager(FakeFactory(FakeAdapter())), gifts=None)
    svc = BusinessService(ctx)
    scheduled = []
    svc.schedule_reply = lambda conv_id, delay=None: scheduled.append(conv_id)
    ctx.business = svc
    return svc, bot, llm, scheduled


async def conv_of(sessions):
    async with sessions() as s:
        return await s.scalar(select(Conversation))


async def test_contact_message_gets_ai_reply_via_business(env, sessions):
    svc, bot, llm, scheduled = env
    llm.responses.append(reply())
    await svc.on_message(msg("Привет, продаёшь подарок?", CONTACT))
    assert scheduled
    await svc.run_agent(scheduled[0])
    sent = [m for m in bot.sent if m["conn"] == "conn1"]
    assert sent and sent[0]["chat_id"] == CONTACT and "интересно" in sent[0]["text"]
    async with sessions() as s:
        senders = [m.sender for m in (await s.scalars(select(ConversationMessage).order_by(ConversationMessage.id))).all()]
    assert senders == ["contact", "agent"]
    # В промпт попадают неизменяемые правила.
    assert "НЕИЗМЕНЯЕМЫЕ ПРАВИЛА" in llm.calls[0]["system"]


async def test_takeover_command_switches_to_manual_and_deletes(env, sessions):
    svc, bot, llm, scheduled = env
    await svc.on_message(msg("Привет", CONTACT, mid=1))
    scheduled.clear()
    await svc.on_message(msg("сутпасмотри", OWNER_TG, mid=2))
    conv = await conv_of(sessions)
    assert conv.mode == "manual"
    assert bot.deleted == [{"conn": "conn1", "ids": [2]}]
    async with sessions() as s:
        texts = [m.text for m in (await s.scalars(select(ConversationMessage))).all()]
    assert "сутпасмотри" not in texts
    # Новое сообщение собеседника — агент молчит.
    await svc.on_message(msg("Ау?", CONTACT, mid=3))
    assert scheduled == []
    assert await svc.run_agent(conv.id) is None
    assert not [m for m in bot.sent if m["conn"]]


async def test_takeover_without_delete_right_reports_honestly(env, sessions):
    svc, bot, llm, scheduled = env
    async with sessions() as s:
        rec = await s.get(BusinessConnectionRecord, "conn1")
        rec.rights = {"can_reply": True, "can_read_messages": True}
        await s.commit()
    await svc.on_message(msg("Привет", CONTACT, mid=1))
    await svc.on_message(msg("сутпасмотри", OWNER_TG, mid=2))
    assert bot.deleted == []
    note = bot.sent[-1]["text"]
    assert "ручной режим" in note and "нет права" in note


async def test_takeover_during_llm_call_prevents_sending(env, sessions):
    svc, bot, llm, scheduled = env
    await svc.on_message(msg("Привет", CONTACT, mid=1))

    class TakeoverLLM(FakeLLM):
        async def generate_json(self, **kw):
            await svc.on_message(msg("сутпасмотри", OWNER_TG, mid=2))
            return reply()

    svc.ctx.llm = TakeoverLLM()
    await svc.run_agent(scheduled[0])
    assert not [m for m in bot.sent if m["conn"]]


async def test_owner_manual_message_pauses_agent(env, sessions):
    svc, bot, llm, scheduled = env
    await svc.on_message(msg("Привет", CONTACT, mid=1))
    scheduled.clear()
    await svc.on_message(msg("Сейчас отвечу сам", OWNER_TG, mid=2))
    await svc.on_message(msg("Ок", CONTACT, mid=3))
    assert scheduled == []


async def test_opt_out_stops_future_replies(env, sessions):
    svc, bot, llm, scheduled = env
    await svc.on_message(msg("Не пишите мне больше", CONTACT, mid=1))
    async with sessions() as s:
        contact = await s.scalar(select(Contact))
        assert contact.opted_out
        contact.opted_out_at = contact.opted_out_at.replace(year=2000)
        await s.commit()
    scheduled.clear()
    await svc.on_message(msg("ещё раз", CONTACT, mid=2))
    assert scheduled == []


async def test_handoff_switches_to_review_and_notifies(env, sessions):
    svc, bot, llm, scheduled = env
    llm.responses.append(reply(text=None, handoff_required=True, handoff_reason="просит живого человека"))
    await svc.on_message(msg("Позовите человека", CONTACT))
    await svc.run_agent(scheduled[0])
    conv = await conv_of(sessions)
    assert conv.mode == "review"
    assert "Нужен человек" in bot.sent[-1]["text"]


async def test_agreed_terms_prepare_deal_for_confirmation(env, sessions, owner):
    svc, bot, llm, scheduled = env
    async with sessions() as s:
        await add_trade_bot(s, owner.id)
        await s.commit()
    upd = reply()["state_update"] | {"conversation_stage": "agreed", "counterparty_role": "seller", "product_type": "NFT",
                                     "item_description": "Plush Pepe #7", "quantity": 1, "agreed_price": "15", "currency": "TON"}
    llm.responses.append(reply(text="Отлично, оформим через бота", state_update=upd, ready_for_deal=True))
    await svc.on_message(msg("Ок, 15 TON за Plush Pepe #7, 1 шт", CONTACT))
    await svc.run_agent(scheduled[0])
    async with sessions() as s:
        deal = await s.scalar(select(Deal))
    assert deal is not None and deal.status == DealStatus.AWAITING_CONFIRMATION
    assert deal.trade_bot_username == "cryptobot"
    assert "подтвердите сделку" in bot.sent[-1]["text"]


async def test_no_trade_bot_means_no_deal(env, sessions):
    svc, bot, llm, scheduled = env
    upd = reply()["state_update"] | {"counterparty_role": "seller", "item_description": "Pepe", "quantity": 1,
                                     "agreed_price": "15", "currency": "TON"}
    llm.responses.append(reply(text="Хорошо", state_update=upd, ready_for_deal=True))
    await svc.on_message(msg("Ок, 15 TON за Pepe, 1 шт", CONTACT))
    await svc.run_agent(scheduled[0])
    async with sessions() as s:
        assert await s.scalar(select(Deal)) is None
    assert "Торговый бот не выбран" in bot.sent[-1]["text"]


async def test_unallowed_connection_is_ignored(env, sessions):
    svc, bot, llm, scheduled = env
    async with sessions() as s:
        rec = await s.get(BusinessConnectionRecord, "conn1")
        rec.allowed = False
        await s.commit()
    await svc.on_message(msg("Привет", CONTACT))
    assert scheduled == [] and await conv_of(sessions) is None
