"""Telegram Premium: catalog, orders, delivery channels, the bot; premium
emoji in the bot and support through a @username."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import httpx
import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from sqlalchemy import select

from starshop.bot import emoji
from starshop.config import get_settings
from starshop.database.enums import OrderStatus, ProductKind
from starshop.database.models import Order, Product
from starshop.delivery import registry as delivery_registry
from starshop.delivery.base import DeliveryError, DeliveryRequest
from starshop.delivery.telegram_premium import TelegramPremiumDeliveryProvider
from starshop.worker.main import delivery_tick
from tests.botkit import USER, FakeSession
from tests.conftest import BOT_TOKEN, create_order, make_admin, pay_demo, set_runtime, tma


@pytest.fixture
async def premium(session) -> Product:
    p = Product(kind=ProductKind.premium, premium_months=3, price=Decimal("1590.00"), cost_price=Decimal("1300.00"), sort_order=500)
    session.add(p)
    await session.commit()
    return p


async def test_premium_order_is_priced_and_delivered(client, session, premium):
    boot = (await client.get("/api/v1/bootstrap")).json()
    plan = next(p for p in boot["catalog"] if p["kind"] == "premium")
    assert plan["premium_months"] == 3 and plan["price"] == "1590.00" and "cost_price" not in plan

    quote = await client.post("/api/v1/orders/quote", json={"product_id": premium.id, "payment_provider": "demo"}, headers=tma())
    assert quote.json()["total"] == "1590.00" and quote.json()["stars_amount"] == 0

    order = await create_order(client, premium.id)
    assert order["premium_months"] == 3 and order["item"] == "Telegram Premium на 3 месяца" and order["stars_amount"] == 0
    await pay_demo(client, order["id"])
    await delivery_tick()
    db_order = await session.get(Order, uuid.UUID(order["id"]), populate_existing=True)
    assert db_order.status == OrderStatus.completed and db_order.cost_amount == Decimal("1300.00")

    # Lucky Buy plays for Stars packages only.
    body = {"product_id": premium.id, "recipient": {"type": "self"}, "payment_provider": "demo", "lucky": {"chance": 20}}
    r = await client.post("/api/v1/orders", json=body, headers={**tma(), "Idempotency-Key": "p" * 16})
    assert r.status_code == 422


def _gift_api(answer: dict, seen: list) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path.rsplit("/", 1)[1], json.loads(request.content)))
        return httpx.Response(200, json=answer)

    return httpx.MockTransport(handler)


def _request(**changes) -> DeliveryRequest:
    data = dict(
        idempotency_key="k",
        order_id=uuid.uuid4(),
        order_number="AB12CD34",
        stars=0,
        recipient_username=None,
        recipient_telegram_id=4242,
        is_demo=False,
        premium_months=6,
    )
    data.update(changes)
    return DeliveryRequest(**data)


async def test_bot_gifts_premium_from_its_stars_balance():
    seen: list = []
    provider = TelegramPremiumDeliveryProvider(get_settings(), transport=_gift_api({"ok": True, "result": True}, seen))
    outcome = await provider.deliver(_request())
    assert outcome.status == "succeeded"
    assert seen == [
        ("giftPremiumSubscription", {"user_id": 4242, "month_count": 6, "star_count": 1500, "text": "Подарок по заказу #AB12CD34"})
    ]

    low = TelegramPremiumDeliveryProvider(
        get_settings(), transport=_gift_api({"ok": False, "description": "Bad Request: BALANCE_TOO_LOW"}, [])
    )
    assert (await low.deliver(_request())).status == "needs_attention"

    with pytest.raises(DeliveryError) as exc:
        await provider.deliver(_request(is_demo=True))
    assert exc.value.definitely_not_executed and len(seen) == 1  # DEMO never spends the bot's Stars


async def test_premium_gift_needs_a_known_user(client, session, premium, settings, monkeypatch):
    monkeypatch.setattr(settings, "premium_delivery_provider", "telegram_premium")
    delivery_registry.override_provider(TelegramPremiumDeliveryProvider(settings))
    r = await client.post("/api/v1/recipients/check", json={"username": "stranger", "product_id": premium.id}, headers=tma())
    assert r.json()["status"] == "unavailable" and r.json()["ok"] is False
    # Stars still go through the main channel, which cannot confirm the account.
    r = await client.post("/api/v1/recipients/check", json={"username": "stranger"}, headers=tma())
    assert r.json()["status"] == "unverified"

    body = {"product_id": premium.id, "recipient": {"type": "username", "username": "stranger"}, "payment_provider": "demo"}
    r = await client.post("/api/v1/orders", json=body, headers={**tma(), "Idempotency-Key": "g" * 16})
    assert r.status_code == 422 and r.json()["error"]["code"] == "recipient_unknown"

    await client.get("/api/v1/me", headers=tma(5555, "friend_known"))
    body["recipient"]["username"] = "friend_known"
    r = await client.post("/api/v1/orders", json=body, headers={**tma(), "Idempotency-Key": "h" * 16})
    assert r.status_code == 201, r.text
    order = (await session.execute(select(Order).execution_options(populate_existing=True))).scalar_one()
    assert order.recipient_telegram_id == 5555 and order.delivery_provider == "telegram_premium"


async def test_premium_in_the_bot(bot_env, session, premium):
    calls, send, press = bot_env
    await send("/start")
    assert "💎 Premium" in calls.last_markup_texts()
    await press("buy:premium")
    assert "Telegram Premium" in calls.texts()[-1]
    assert "💎 Telegram Premium на 3 месяца · 1\u202f590 ₽" in calls.last_markup_texts()
    await press(f"buy:pkg:{premium.id}")
    assert "Кому покупаем <b>💎 Telegram Premium на 3 месяца</b>" in calls.texts()[-1]
    await press("buy:self")
    assert "Подписка: <b>Telegram Premium на 3 месяца</b>" in calls.texts()[-1]
    await press("buy:pay:demo")
    await session.commit()
    order = (await session.execute(select(Order).execution_options(populate_existing=True))).scalar_one()
    assert order.premium_months == 3 and order.stars_amount == 0 and order.total == Decimal("1590.00")


# --- premium emoji ----------------------------------------------------------------


async def test_premium_emoji_in_menu_with_fallback(bot_env, session):
    calls, send, _ = bot_env
    await set_runtime(session, "bot_emoji", enabled=True, ids={"welcome": "5368324170671202286", "stars": "5377498341074542641"})
    await send("/start")
    sent = [m for m in calls.calls if isinstance(m, SendMessage)][-1]
    assert '<tg-emoji emoji-id="5368324170671202286">✨</tg-emoji>' in sent.text
    stars = next(b for row in sent.reply_markup.inline_keyboard for b in row if b.callback_data == "buy:start")
    assert stars.icon_custom_emoji_id == "5377498341074542641" and stars.text == "Купить Stars"

    stripped = emoji.strip_custom(sent)
    assert "<tg-emoji" not in stripped.text and "✨" in stripped.text
    button = next(b for row in stripped.reply_markup.inline_keyboard for b in row if b.callback_data == "buy:start")
    assert button.icon_custom_emoji_id is None and button.text == "⭐️ Купить Stars"


async def test_refused_custom_emoji_are_sent_as_usual_ones():
    class Picky(FakeSession):
        async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109
            if emoji.has_custom(method):
                self.calls.append(method)
                raise TelegramBadRequest(method=method, message="Bad Request: custom emoji are not allowed")
            return await super().make_request(bot, method, timeout)

    api = Picky()
    bot = emoji.install(Bot(BOT_TOKEN, session=api))
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Магазин", callback_data="x", icon_custom_emoji_id="123456")]]
    )
    emoji.ICON_FALLBACK["123456"] = "🌐"
    await bot.send_message(777, 'Hi <tg-emoji emoji-id="123456">✨</tg-emoji>', reply_markup=markup, parse_mode="HTML")
    last = api.calls[-1]
    assert last.text == "Hi ✨" and last.reply_markup.inline_keyboard[0][0].text == "🌐 Магазин"


async def test_admin_learns_premium_emoji_ids(bot_env, session):
    calls, send, _ = bot_env
    await make_admin(session, telegram_id=USER.id)
    from datetime import UTC, datetime

    from aiogram.types import Chat, Message, Update

    from tests.botkit import dispatcher

    msg = Message(
        message_id=50,
        date=datetime.now(UTC),
        chat=Chat(id=USER.id, type="private"),
        from_user=USER,
        text="🔥",
        entities=[MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="5368324170671202286")],
    )
    await dispatcher().feed_update(Bot(BOT_TOKEN, session=calls), Update(update_id=50, message=msg))
    assert "<code>5368324170671202286</code>" in calls.texts()[-1]

    bad = await set_runtime_bad(session)
    assert bad


async def set_runtime_bad(session) -> bool:
    from starshop.services.app_settings import save_setting

    try:
        await save_setting(session, "bot_emoji", {"enabled": True, "ids": {"stars": "not-a-number"}}, None)
    except ValueError:
        return True
    return False


# --- support through a username ------------------------------------------------------


async def test_support_is_a_telegram_account(bot_env, session):
    calls, send, press = bot_env
    await set_runtime(
        session,
        "content",
        support={"telegram": "@pulsar_help", "email": "", "hours": "Ежедневно 10–22", "response_time": "Ответ за 15 минут"},
    )
    await send("/start")
    sent = [m for m in calls.calls if isinstance(m, SendMessage)][-1]
    support = next(b for row in sent.reply_markup.inline_keyboard for b in row if "Поддержка" in b.text)
    assert support.url == "https://t.me/pulsar_help" and support.callback_data is None
    await press("menu:support")
    assert "@pulsar_help" in calls.texts()[-1]
    await send("/support")
    assert "Напишите нам: @pulsar_help" in calls.texts()[-1]
