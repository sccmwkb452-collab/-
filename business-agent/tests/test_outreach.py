from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from sqlalchemy import select

from app.business.sender import BusinessSender
from app.db.models import BusinessConnectionRecord, Contact, InitialTemplate, OutreachTask, Owner
from app.outreach.service import OutreachService
from tests.conftest import OWNER_TG, FakeBot


class Biz:
    def __init__(self, bot):
        self.sender = BusinessSender(bot)
        self.notes = []

    async def notify(self, tg, text, reply_markup=None):
        self.notes.append(text)


async def _setup(s, owner_id, *, username_only=False, opted=False):
    s.add(BusinessConnectionRecord(id="conn1", owner_id=owner_id, user_telegram_id=OWNER_TG, user_chat_id=OWNER_TG,
                                   is_enabled=True, allowed=True, rights={"can_reply": True}))
    s.add(InitialTemplate(owner_id=owner_id, text="Здравствуйте! Интересует ваш подарок?", is_primary=True, allow_adaptation=False))
    c = Contact(owner_id=owner_id, telegram_user_id=None if username_only else 777, username="target", profile={},
                opted_out=opted)
    s.add(c)
    await s.flush()
    t = OutreachTask(owner_id=owner_id, contact_id=c.id, status="approved")
    s.add(t)
    await s.flush()
    return t


def service(sessions, bot):
    ctx = SimpleNamespace(sessions=sessions, llm=None)
    biz = Biz(bot)
    return OutreachService(ctx, biz), biz


async def test_sends_when_telegram_allows(sessions, owner):
    bot = FakeBot()
    async with sessions() as s:
        await _setup(s, owner.id)
        await s.commit()
    svc, biz = service(sessions, bot)
    await svc.process_owner(owner.id)
    async with sessions() as s:
        task = await s.scalar(select(OutreachTask))
        assert task.status == "sent" and task.sent_message_id
        assert (await s.scalar(select(Contact))).last_contacted_at is not None
    # Пауза между обращениями: второй вызов ничего не делает.
    await svc.process_owner(owner.id)
    assert len([m for m in bot.sent if m["conn"]]) == 1


async def test_manual_when_bot_cannot_start_chat(sessions, owner):
    bot = FakeBot()
    bot.send_error = TelegramBadRequest(method=SendMessage(chat_id=1, text="x"), message="Bad Request: chat not found")
    async with sessions() as s:
        await _setup(s, owner.id)
        await s.commit()
    svc, biz = service(sessions, bot)
    await svc.process_owner(owner.id)
    async with sessions() as s:
        task = await s.scalar(select(OutreachTask))
    assert task.status == "manual_required"
    assert "вручную" in biz.notes[-1] and "Здравствуйте" in biz.notes[-1]


async def test_username_only_contact_goes_manual(sessions, owner):
    bot = FakeBot()
    async with sessions() as s:
        await _setup(s, owner.id, username_only=True)
        await s.commit()
    svc, biz = service(sessions, bot)
    await svc.process_owner(owner.id)
    assert not [m for m in bot.sent if m["conn"]]
    assert "t.me/target" in biz.notes[-1]


async def test_opted_out_contact_is_never_contacted(sessions, owner):
    bot = FakeBot()
    async with sessions() as s:
        await _setup(s, owner.id, opted=True)
        await s.commit()
    svc, biz = service(sessions, bot)
    await svc.process_owner(owner.id)
    async with sessions() as s:
        assert (await s.scalar(select(OutreachTask))).status == "cancelled"
    assert bot.sent == []


async def test_paused_owner_sends_nothing(sessions, owner):
    bot = FakeBot()
    async with sessions() as s:
        await _setup(s, owner.id)
        (await s.get(Owner, owner.id)).paused = True
        await s.commit()
    svc, _ = service(sessions, bot)
    await svc.process_owner(owner.id)
    assert bot.sent == []
