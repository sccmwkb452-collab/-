"""Telegram bot through the real aiogram dispatcher with a fake Bot API session."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendDocument, SendMessage, SendPhoto, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from sqlalchemy import select

from autocommerce.bot.main import build_dispatcher
from autocommerce.database.enums import OrderStatus
from autocommerce.database.models import Order
from autocommerce.database.session import get_sessionmaker
from autocommerce.services import autosettings

from .conftest import BOT_TOKEN, OWNER_ID
from .factories import make_product

pytestmark = pytest.mark.usefixtures("seeded")
OWNER = User(id=OWNER_ID, is_bot=False, first_name="Owner", username="owner")
STRANGER = User(id=555, is_bot=False, first_name="Stranger")
MAIN_MENU = [
    "🏠 Главная панель",
    "📦 Товары",
    "🛒 Заказы",
    "💬 Сообщения покупателей",
    "📈 Аналитика",
    "💰 Прибыль и цены",
    "🔎 Поиск товаров",
    "🏪 Поставщики",
    "🖼 Генератор изображений",
    "📝 Объявления",
    "⚙️ Автонастройки",
    "📊 Отчёты",
    "🛡 Безопасность",
    "🔔 Уведомления",
    "🧾 Журнал операций",
    "⚙️ Настройки",
]


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:  # noqa: ASYNC109
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText, SendPhoto, SendDocument)):
            return Message(
                message_id=len(self.calls),
                date=datetime.now(UTC),
                chat=Chat(id=OWNER_ID, type="private"),
                text=getattr(method, "text", None),
            )
        if isinstance(method, AnswerCallbackQuery):
            return True
        return True

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:  # pragma: no cover
        yield b""

    def texts(self) -> list[str]:
        return [m.text for m in self.calls if isinstance(m, (SendMessage, EditMessageText))]

    def last_buttons(self) -> list[str]:
        for m in reversed(self.calls):
            if isinstance(m, (SendMessage, EditMessageText)) and m.reply_markup is not None:
                return [b.text for row in m.reply_markup.inline_keyboard for b in row]
        return []

    def alerts(self) -> list[str]:
        return [m.text for m in self.calls if isinstance(m, AnswerCallbackQuery) and m.text]


@pytest.fixture
def bot_env():
    session = FakeSession()
    bot = Bot(BOT_TOKEN, session=session)
    dp = build_dispatcher()
    dp.fsm.storage = MemoryStorage()
    counter = {"n": 0}

    async def send(text: str, user: User = OWNER) -> None:
        counter["n"] += 1
        msg = Message(message_id=counter["n"], date=datetime.now(UTC), chat=Chat(id=user.id, type="private"), from_user=user, text=text)
        await dp.feed_update(bot, Update(update_id=counter["n"], message=msg))

    async def press(data: str, user: User = OWNER) -> None:
        counter["n"] += 1
        msg = Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=user.id, type="private"), text="screen")
        cq = CallbackQuery(id=str(counter["n"]), from_user=user, chat_instance="ci", data=data, message=msg)
        await dp.feed_update(bot, Update(update_id=counter["n"], callback_query=cq))

    return session, send, press


def no_errors(session: FakeSession) -> None:
    bad = [t for t in session.texts() + session.alerts() if "Внутренняя ошибка" in (t or "")]
    assert not bad, bad


async def test_owner_gets_main_menu_and_stranger_is_denied(bot_env):
    session, send, _ = bot_env
    await send("/start")
    assert session.last_buttons() == MAIN_MENU
    assert "Тестовый режим" in session.texts()[-1]
    await send("/start", STRANGER)
    assert "Нет доступа" in session.texts()[-1] and "555" in session.texts()[-1]
    assert len(session.calls) == 2  # nothing else is shown to a stranger


async def test_every_main_section_opens(bot_env):
    session, _, press = bot_env
    await make_product()
    for cb in [
        "dash",
        "prd:list:all:1",
        "ord:home",
        "msg:home",
        "ana:30d",
        "prc:home",
        "res:home",
        "sup:list",
        "img:home",
        "lst:home",
        "as:home",
        "rep:home",
        "sec:home",
        "ntf:home",
        "log:home",
        "set:home",
    ]:
        before = len(session.calls)
        await press(cb)
        assert len(session.calls) > before, cb
        no_errors(session)
        assert "🏠 Меню" in session.last_buttons() or "‹ Назад в меню" in session.last_buttons(), cb


async def test_autosettings_menu_matches_the_screenshot_list(bot_env):
    session, _, press = bot_env
    await press("as:home")
    labels = session.last_buttons()
    assert labels[:14] == [f.label for f in autosettings.FEATURES]
    assert labels[-1] == "‹ Назад в меню"
    for f in autosettings.FEATURES:
        await press(f"as:open:{f.code}")
        text = session.texts()[-1]
        assert f.title in text and "Статус" in text and "Интеграция" in text
        buttons = session.last_buttons()
        assert "👁 Предпросмотр" in buttons and "🧪 Тест" in buttons and "♻️ Сбросить" in buttons and "🕓 История" in buttons
        await press(f"as:test:{f.code}")
        await press(f"as:prev:{f.code}")
    no_errors(session)
    await press("as:open:auto_confirm")
    assert "🔴 Интеграция недоступна" in session.last_buttons()


async def test_toggle_edit_and_reset_in_bot(bot_env):
    session, send, press = bot_env
    await press("as:tog:greeting:1")
    await press("as:f:greeting:text")
    await send("Привет, {buyer}! Это {shop}.")
    async with get_sessionmaker()() as s:
        d = await autosettings.details(s, "greeting")
    assert d["enabled"] and d["config"]["text"] == "Привет, {buyer}! Это {shop}."
    await press("as:f:greeting:text")
    await send("Ошибка {nope}")
    assert "Неизвестные переменные" in session.texts()[-1]
    await press("as:reset:greeting")
    await press("as:reset:greeting:y")
    async with get_sessionmaker()() as s:
        d = await autosettings.details(s, "greeting")
    assert d["config"]["text"] == autosettings.feature("greeting").defaults["text"]


async def test_new_order_wizard_creates_and_processes_order(bot_env):
    session, send, press = bot_env
    pid = await make_product(name="Steam Wallet 20 USD", manual_cost="1000")
    await press("ord:new")
    assert any("Steam Wallet 20 USD" in b for b in session.last_buttons())
    await press(f"ord:np:{pid}")
    await send("DEAL-777")
    await send("+")
    await send("gamer777 -")
    assert "Заказ создан" in session.texts()[-1]
    async with get_sessionmaker()() as s:
        order = (await s.execute(select(Order))).scalar_one()
    assert order.external_id == "DEAL-777" and order.buyer_name == "gamer777"
    await press(f"ord:np:{pid}")
    await send("DEAL-777")
    await send("+")
    await send("-")
    assert "уже внесена" in session.texts()[-1]  # duplicate deal is not created twice
    await press(f"ord:open:{order.id}")
    assert order.number in session.texts()[-1]
    no_errors(session)


async def test_dangerous_actions_need_confirmation(bot_env):
    session, _, press = bot_env
    await press("sec:kill:on")
    assert "Подтвердите действие" in session.texts()[-1]
    async with get_sessionmaker()() as s:
        from autocommerce.services import app_settings

        assert not await app_settings.automation_stopped(s)
    await press("sec:kill:on:y")
    async with get_sessionmaker()() as s:
        assert await app_settings.automation_stopped(s)


async def test_pricing_calculator_in_bot(bot_env):
    session, send, press = bot_env
    await press("prc:calc")
    await send("900 RUB 10 1300")
    text = session.texts()[-1]
    assert "Минимальная цена" in text and "При цене" in text


async def test_record_message_and_review_from_bot(bot_env):
    session, send, press = bot_env
    pid = await make_product()
    await press("ord:new")
    await press(f"ord:np:{pid}")
    await send("DEAL-1")
    await send("+")
    await send("buyer1 @buyer1")
    async with get_sessionmaker()() as s:
        order = (await s.execute(select(Order))).scalar_one()
    await press(f"msg:new:{order.id}")
    await send("Здравствуйте, когда будет код?")
    assert "Сообщение записано" in session.texts()[-1]
    await press(f"msg:review:{order.id}")
    await send("5 Всё отлично")
    assert "Отзыв сохранён" in session.texts()[-1]
    no_errors(session)
    assert order.status in (OrderStatus.NEW, OrderStatus.PENDING_REVIEW, OrderStatus.PENDING_PURCHASE)
