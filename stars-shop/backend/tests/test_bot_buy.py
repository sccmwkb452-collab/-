"""Buying Stars in the chat, Telegram Stars payments and the FSM storage."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from aiogram import Bot
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import AnswerPreCheckoutQuery
from aiogram.types import Chat, Message, PreCheckoutQuery, SuccessfulPayment, Update
from sqlalchemy import func, select

from starshop.bot.handlers.buy import BuyFlow
from starshop.bot.storage import DbStorage
from starshop.config import get_settings
from starshop.database.enums import OrderStatus, ProductKind
from starshop.database.models import LuckyDraw, Order, Payment, Product
from starshop.payments import registry as payment_registry
from starshop.payments.telegram_stars import TelegramStarsProvider
from starshop.services import lucky
from starshop.worker.main import delivery_tick
from tests.botkit import USER, FakeSession, dispatcher
from tests.conftest import BOT_TOKEN, create_order, get_user, tma


def buttons(calls: FakeSession) -> dict[str, str]:
    """Text → callback data (or url) of the last keyboard."""
    for m in reversed(calls.calls):
        markup = getattr(m, "reply_markup", None)
        if markup is not None and getattr(markup, "inline_keyboard", None):
            return {b.text: b.callback_data or b.url or "" for row in markup.inline_keyboard for b in row}
    return {}


async def _orders(session) -> list[Order]:
    await session.commit()
    return list((await session.execute(select(Order).execution_options(populate_existing=True))).scalars())


async def test_buy_a_package_for_myself(bot_env, session, product):
    calls, send, press = bot_env
    await send("/start")
    await press("buy:start")
    kb = buttons(calls)
    assert "Выберите пакет или укажите своё количество" in calls.texts()[-1]
    assert kb["100 ⭐️ · 169 ₽"] == f"buy:pkg:{product.id}"

    await press(f"buy:pkg:{product.id}")
    assert "Кому покупаем <b>⭐️ 100 Stars</b>" in calls.texts()[-1]
    await press("buy:self")
    summary = calls.texts()[-1]
    assert "Проверьте заказ" in summary and "Получатель: себе" in summary and "169 ₽" in summary
    pay_button = next(t for t in buttons(calls) if t.startswith("💳 Оплатить"))
    assert pay_button == "💳 Оплатить 169 ₽ · DEMO-оплата"

    await press("buy:pay:demo")
    assert "Заказ #" in calls.texts()[-1] and "создан" in calls.texts()[-1]
    # A second tap on the old summary does not create a second order.
    await press("buy:pay:demo")
    orders = await _orders(session)
    assert len(orders) == 1 and orders[0].status == OrderStatus.pending_payment and orders[0].recipient_type == "self"

    payment = (await session.execute(select(Payment))).scalar_one()
    await press(f"pay:demo:{payment.id}")
    assert "Оплачен" in calls.texts()[-1]
    await delivery_tick()
    (order,) = await _orders(session)
    assert order.status == OrderStatus.completed


async def test_own_amount_and_gift_with_checks(bot_env, session, custom_product):
    calls, send, press = bot_env
    await send("/start")
    await press("buy:custom")
    assert "от <b>50</b> до <b>10" in calls.texts()[-1]
    await send("много")
    assert "целое число" in calls.texts()[-1]
    await send("10")
    assert "от 50 до 10000" in calls.texts()[-1]
    await send("750")
    assert "Кому покупаем <b>⭐️ 750 Stars</b>" in calls.texts()[-1]

    await press("buy:other")
    await send("@bad name")
    assert "username" in calls.texts()[-1]
    # DEMO delivery cannot confirm an account: the customer is told so.
    await send("@some_friend")
    summary = calls.texts()[-1]
    assert "Проверьте заказ" in summary and "⚠️ @some_friend" in summary and "Не удалось подтвердить" in summary
    assert "1 237,50 ₽" in summary  # 750 × 1.65, calculated on the server

    # A user of the shop is recognised.
    await send("/start", user=type(USER)(id=4242, is_bot=False, first_name="Борис", username="boris_shop"))
    await press("buy:recipient")
    await send("boris_shop")
    assert "✅ Борис (@boris_shop)" in calls.texts()[-1]

    await press("buy:pay:demo")
    (order,) = await _orders(session)
    assert order.stars_amount == 750 and order.recipient_username == "boris_shop" and order.recipient_telegram_id == 4242
    assert order.total == Decimal("1237.50")


async def test_cancel_and_stale_buttons(bot_env, session, product):
    calls, send, press = bot_env
    await send("/start")
    await press(f"buy:pkg:{product.id}")
    await press("buy:cancel")
    assert "Покупка отменена" in calls.texts()[-1]
    await press("buy:self")  # the dialogue is over
    assert await session.scalar(select(func.count()).select_from(Order)) == 0


async def test_db_storage_keeps_dialogues_per_user():
    storage = DbStorage()
    anna = StorageKey(bot_id=1, chat_id=777, user_id=777)
    boris = StorageKey(bot_id=1, chat_id=888, user_id=888)
    await storage.set_state(anna, BuyFlow.amount)
    await storage.set_data(anna, {"product_id": 5})
    assert await storage.get_state(anna) == BuyFlow.amount.state
    assert await storage.get_data(anna) == {"product_id": 5}
    assert await storage.get_state(boris) is None and await storage.get_data(boris) == {}
    await storage.set_state(anna, None)
    await storage.set_data(anna, {})
    assert await storage.get_state(anna) is None and await storage.get_data(anna) == {}


# --- Telegram Stars -------------------------------------------------------------


@pytest.fixture
async def prize(session) -> Product:
    p = Product(kind=ProductKind.package, stars_amount=1000, price=Decimal("1549.00"), sort_order=1)
    session.add(p)
    await session.commit()
    return p


@pytest.fixture
def stars_api(settings, monkeypatch):
    """Telegram Bot API for createInvoiceLink / refundStarPayment."""
    monkeypatch.setattr(settings, "payment_providers", ["demo", "telegram_stars"])
    seen: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[1]
        body = json.loads(request.content or b"{}")
        seen.append((method, body))
        if method == "createInvoiceLink":
            return httpx.Response(200, json={"ok": True, "result": "https://t.me/$invoice_abc"})
        return httpx.Response(200, json={"ok": True, "result": True})

    payment_registry.override_provider(TelegramStarsProvider(get_settings(), transport=httpx.MockTransport(handler)))
    return seen


async def test_lucky_attempt_paid_with_telegram_stars(client, session, prize, stars_api, bot_env):
    calls, send, _ = bot_env
    boot = (await client.get("/api/v1/bootstrap")).json()
    assert [m["id"] for m in boot["lucky"]["payment_methods"]] == ["demo", "telegram_stars"]
    # Stars are not offered for regular purchases in roubles.
    assert "telegram_stars" not in [m["id"] for m in boot["payment_methods"]]

    order = await create_order(client, prize.id, provider="telegram_stars", lucky={"chance": 20}, telegram_id=777, username="anna_buyer")
    assert Decimal(order["total"]) == 200 and order["currency"] == "XTR"
    r = await client.post(
        f"/api/v1/orders/{order['id']}/payment",
        json={"provider": "telegram_stars", "client_seed": "seed-from-app-1"},
        headers=tma(777, "anna_buyer"),
    )
    payment = r.json()
    assert payment["pay_url"] == "https://t.me/$invoice_abc" and payment["pay_url_kind"] == "invoice"
    method, body = stars_api[0]
    assert method == "createInvoiceLink" and body["currency"] == "XTR" and body["prices"] == [{"label": "1000 Stars", "amount": 200}]
    assert body["payload"] == payment["id"]

    dp = dispatcher()
    bot = Bot(BOT_TOKEN, session=calls)

    async def pre_checkout(amount: int, uid: int = 777) -> AnswerPreCheckoutQuery:
        q = PreCheckoutQuery(
            id="pcq",
            from_user=type(USER)(id=uid, is_bot=False, first_name="X"),
            currency="XTR",
            total_amount=amount,
            invoice_payload=payment["id"],
        )
        await dp.feed_update(bot, Update(update_id=100 + amount + uid, pre_checkout_query=q))
        return [m for m in calls.calls if isinstance(m, AnswerPreCheckoutQuery)][-1]

    assert (await pre_checkout(150)).ok is False  # wrong amount
    assert (await pre_checkout(200, uid=999)).ok is False  # someone else's invoice
    assert (await pre_checkout(200)).ok is True

    async def paid(update_id: int) -> None:
        msg = Message(
            message_id=update_id,
            date=datetime.now(UTC),
            chat=Chat(id=777, type="private"),
            from_user=USER,
            successful_payment=SuccessfulPayment(
                currency="XTR",
                total_amount=200,
                invoice_payload=payment["id"],
                telegram_payment_charge_id="charge-1",
                provider_payment_charge_id="",
            ),
        )
        await dp.feed_update(bot, Update(update_id=update_id, message=msg))

    await paid(500)
    await paid(501)  # the same charge again: processed once
    assert "Оплата получена" in calls.texts()[-2]
    await session.commit()
    draws = (await session.execute(select(LuckyDraw).execution_options(populate_existing=True))).scalars().all()
    assert len(draws) == 1 and draws[0].drawn_at is not None
    db_order = await session.get(Order, draws[0].order_id, populate_existing=True)
    assert db_order.status in (OrderStatus.paid, OrderStatus.lost)
    db_payment = await session.get(Payment, uuid.UUID(payment["id"]), populate_existing=True)
    assert db_payment.provider_data["confirmation"]["telegram_payment_charge_id"] == "charge-1"
    assert db_payment.currency == lucky.CURRENCY
    assert (await get_user(session, 777)).bot_started
