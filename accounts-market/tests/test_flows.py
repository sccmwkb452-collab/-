"""End-to-end walks through the bot with a fake Telegram API."""

from __future__ import annotations

import pytest_asyncio
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import func, select

from bot.callbacks import Adm, Cat, Prod
from database.models import Category, Order, Payment, PaymentStatus, Product, User
from tests.conftest import ADMIN_ID, make_product
from tests.telegram_mock import Client


@pytest_asyncio.fixture(loop_scope="session")
async def env(dispatcher_env, sm):
    dp, bot, tg = dispatcher_env
    tg.chats.clear()
    tg.answers.clear()
    await dp.storage.close()
    dp.fsm.storage = MemoryStorage()
    return dispatcher_env


def client(env, user_id: int, username: str = "buyer") -> Client:
    dp, bot, tg = env
    return Client(dp, bot, tg, user_id, username)


async def test_start_shows_branded_menu(env):
    c = client(env, 500)
    await c.send("/start")
    assert c.last.photo, "home screen must have a banner"
    assert "⚡ <b>ACCOUNTS MARKET</b>" in c.last.html_text or "ACCOUNTS MARKET" in c.screen
    assert "Добро пожаловать в магазин цифровых товаров" in c.screen
    labels = c.buttons()
    for label in ["🛍 Каталог", "🔥 Популярное", "👤 Личный кабинет", "💎 Пополнить баланс",
                  "📦 Мои покупки", "🎁 Реферальная программа", "🆘 Поддержка", "📜 Правила магазина"]:
        assert label in labels
    assert "🛠 Админ-панель" not in labels


async def test_catalog_walkthrough_and_purchase(env, sm):
    product = await make_product(sm, price=1490_00, stock=2, title="Premium Product", region="EU",
                                 short_description="Short", specs="Срок: 12 месяцев\nПочта: есть")
    c = client(env, 501)
    await c.send("/start")
    menu_id = c.last.message_id

    await c.click("🛍 Каталог")
    assert c.last.message_id == menu_id, "navigation must edit the same message"
    assert "Каталог" in c.screen
    await c.click("Cat Premium Product")
    assert "Premium Product" in c.screen and "1 490" in c.screen and "EU" in c.screen

    await c.click("ℹ️ Premium Product")
    assert "PREMIUM PRODUCT" in c.screen and "Стоимость" in c.screen and "в наличии · 2 шт." in c.screen
    assert "SECRET" not in c.screen, "unit content must stay hidden before purchase"
    assert any("Купить за 1" in b for b in c.buttons())

    # No money yet: offer a top-up
    await c.click("🛒 Купить за")
    assert "Недостаточно средств" in c.screen
    assert "💎 Пополнить баланс" in c.buttons() and "◀️ Вернуться к товару" in c.buttons()

    # Top up in DEMO mode through the same buttons a user would press
    await c.click("💎 Пополнить баланс")
    assert "DEMO" in c.screen
    await c.click("2 500 ₽")
    assert "Счёт на пополнение" in c.screen
    await c.click("🔄 Проверить оплату")  # nothing paid yet
    async with sm() as s:
        assert (await s.get(User, 501)).balance == 0
    await c.click("🧪 DEMO: провести оплату")
    async with sm() as s:
        assert (await s.get(User, 501)).balance == 2500_00
    assert "зачислено" in c.screen
    _, _, tg = env
    assert any("Оплата получена" in (m.text or "") for m in tg.chats[501])

    # Back to the product and buy it
    await c.press(Prod(id=product.id).pack())
    await c.click("🛒 Купить за")
    assert "Подтверждение покупки" in c.screen and "Баланс после покупки" in c.screen
    confirm_message = c.last
    await c.click("✅ Подтвердить")
    delivered = [m for m in tg.chats[501] if m.text and "Данные товара" in m.text]
    assert len(delivered) == 1 and "SECRET-Premium Product" in delivered[0].text
    success = next(m for m in tg.chats[501] if m.caption and "оформлен" in m.caption)
    assert "AM-" in success.caption

    # Tapping «Confirm» again on the same screen must not charge twice
    await c.press(confirm_message.reply_markup.inline_keyboard[0][0].callback_data, success)
    async with sm() as s:
        assert await s.scalar(select(func.count(Order.id))) == 1
        assert (await s.get(User, 501)).balance == 1010_00
    assert len([m for m in tg.chats[501] if m.text and "Данные товара" in m.text]) == 1

    # The order is in the history with its content
    await c.send("/start")
    await c.click("📦 Мои покупки")
    assert "Всего заказов: 1" in c.screen
    await c.click("✅ AM-")
    assert "SECRET-Premium Product" in c.screen
    assert "📋 Скопировать данные" in c.buttons()


async def test_profile_sections(env, sm):
    c = client(env, 502)
    await c.send("/start")
    await c.click("👤 Личный кабинет")
    assert "Telegram ID: <code>502</code>" in c.last.html_text or "502" in c.screen
    for label, expected in [("💳 История операций", "История операций"), ("🧾 Пополнения", "История пополнений"),
                            ("📦 История заказов", "Мои покупки"), ("🎁 Мои рефералы", "Реферальная программа")]:
        await c.send("/profile")
        await c.click(label)
        assert expected in c.screen, label


async def test_referral_link_and_signup(env, sm):
    inviter = client(env, 503, "inviter")
    await inviter.send("/start")
    await inviter.click("🎁 Реферальная программа")
    async with sm() as s:
        code = (await s.get(User, 503)).ref_code
    assert f"https://t.me/test_shop_bot?start=ref_{code}" in inviter.screen
    assert "📤 Поделиться ссылкой" in inviter.buttons()

    friend = client(env, 504, "friend")
    await friend.send(f"/start ref_{code}")
    async with sm() as s:
        assert (await s.get(User, 504)).referrer_id == 503
    _, _, tg = env
    assert any("зарегистрировался" in (m.text or "") for m in tg.chats[503])

    # self-referral and re-attaching do nothing
    await inviter.send(f"/start ref_{code}")
    other = client(env, 505)
    await other.send("/start")
    await other.send(f"/start ref_{code}")
    async with sm() as s:
        assert (await s.get(User, 503)).referrer_id is None
        assert (await s.get(User, 505)).referrer_id is None


async def test_popular_support_rules(env, sm):
    await make_product(sm, title="Hot item", is_featured=True)
    c = client(env, 506)
    await c.send("/start")
    await c.click("🔥 Популярное")
    assert "Hot item" in c.screen
    await c.click("🏠 Главное меню")
    await c.click("🆘 Поддержка")
    assert "Поддержка" in c.screen
    await c.click("📜 Правила магазина")
    assert "Правила магазина" in c.screen


async def test_custom_topup_amount(env, sm):
    c = client(env, 507)
    await c.send("/start")
    await c.click("💎 Пополнить баланс")
    await c.click("✍️ Другая сумма")
    await c.send("10")
    assert "Укажите сумму" in c.screen
    await c.send("750")
    assert "750" in c.screen and "Счёт на пополнение" in c.screen
    async with sm() as s:
        assert (await s.scalar(select(Payment))).amount == 750_00


async def test_stale_and_foreign_buttons(env, sm):
    c = client(env, 508)
    await c.send("/start")
    await c.press("totally:unknown")
    assert "устарела" in c.last_answer().text
    await c.press(Cat(id=9999).pack())
    assert "недоступна" in c.last_answer().text
    await c.press(Prod(id=9999).pack())
    assert "недоступен" in c.last_answer().text
    # A regular user cannot open admin screens even with a crafted callback
    await c.press(Adm(s="stats").pack())
    assert "Статистика" not in c.screen
    await c.send("/admin")
    assert "Админ-панель" not in c.screen


async def test_banned_user_is_blocked(env, sm):
    c = client(env, 509)
    await c.send("/start")
    async with sm() as s, s.begin():
        user = await s.get(User, 509)
        user.is_banned, user.ban_reason = True, "spam"
    await c.send("/start")
    assert "ограничен" in c.screen and "spam" in c.screen


async def test_admin_panel_walkthrough(env, sm):
    product = await make_product(sm, price=500_00, stock=1, title="Admin item")
    a = client(env, ADMIN_ID, "admin")
    await a.send("/start")
    assert "🛠 Админ-панель" in a.buttons()
    await a.click("🛠 Админ-панель")
    for section, expected in [("📊 Статистика", "Статистика"), ("📦 Товары", "Товары"), ("🗂 Категории", "Категории"),
                              ("🛒 Заказы", "Заказы"), ("👥 Пользователи", "Пользователи"), ("💳 Платежи", "Все платежи"),
                              ("📢 Рассылки", "Рассылки"), ("⚙️ Настройки", "Настройки магазина")]:
        await a.send("/admin")
        await a.click(section)
        assert expected in a.screen, section

    # Edit price through FSM
    await a.press(Adm(s="prod", id=product.id).pack())
    await a.click("💰 Цена")
    await a.send("abc")
    assert "Некорректная" in a.screen
    await a.send("990")
    async with sm() as s:
        assert (await s.get(Product, product.id)).price == 990_00

    # Add stock units
    await a.press(Adm(s="pstock", id=product.id).pack())
    await a.click("➕ Добавить единицы")
    await a.send("unit-1\nunit-2\n\nunit-3")
    assert "доступно к продаже: <b>4</b>" in a.last.html_text.lower() or "4" in a.screen

    # Archive and back
    await a.press(Adm(s="prod", id=product.id).pack())
    await a.click("🗄 В архив")
    async with sm() as s:
        assert (await s.get(Product, product.id, populate_existing=True)).is_archived
    await a.click("♻️ Вернуть в продажу")

    # Create a product with the wizard
    await a.press(Adm(s="pnew").pack())
    await a.click("Cat Admin item")
    await a.send("Wizard product")
    await a.send("1 200")
    await a.send("-")
    async with sm() as s:
        assert (await s.scalar(select(Product).where(Product.title == "Wizard product"))).price == 1200_00

    # Category
    await a.press(Adm(s="cats").pack())
    await a.click("➕ Новая категория")
    await a.send("🎮 Игровые товары")
    async with sm() as s:
        cat = await s.scalar(select(Category).where(Category.title == "Игровые товары"))
        assert cat.emoji == "🎮"

    # Settings: shop name and referral percent with validation
    await a.press(Adm(s="sete", v="shop_name").pack())
    await a.send("NEW STORE")
    await a.press(Adm(s="sete", v="referral_percent").pack())
    await a.send("99")
    assert "от 0 до 50" in a.screen
    await a.send("7")
    await a.send("/start")
    assert "NEW STORE" in a.screen


async def test_admin_balance_adjustment_and_refund(env, sm):
    buyer = client(env, 510, "buyer510")
    await buyer.send("/start")
    a = client(env, ADMIN_ID, "admin")
    await a.send("/admin")
    await a.press(Adm(s="usr", id=510).pack())
    await a.click("➕➖ Изменить баланс")
    await a.send("+2000")
    await a.send("x")  # too short a reason
    assert "от 3 до 256" in a.screen
    await a.send("Компенсация по обращению")
    await a.click("✅ Подтвердить")
    confirm_msg = a.last
    async with sm() as s:
        assert (await s.get(User, 510)).balance == 2000_00
    # a repeated tap on the old confirmation does nothing
    await a.press(Adm(s="ubalok", id=510).pack(), confirm_msg)
    async with sm() as s:
        assert (await s.get(User, 510)).balance == 2000_00

    product = await make_product(sm, price=800_00, stock=1, title="Refundable")
    await buyer.press(Prod(id=product.id).pack(), buyer.tg.chats[510][0])
    await buyer.click("🛒 Купить за")
    await buyer.click("✅ Подтвердить")
    async with sm() as s:
        order = await s.scalar(select(Order))
        assert (await s.get(User, 510)).balance == 1200_00

    await a.press(Adm(s="osearch").pack())
    await a.send(order.number)
    assert order.number in a.screen
    await a.click("↩️ Отменить и вернуть средства")
    await a.send("Товар не подошёл")
    await a.click("↩️ Вернуть средства")
    async with sm() as s:
        assert (await s.get(User, 510)).balance == 2000_00
        assert (await s.get(Order, order.id, populate_existing=True)).status == "refunded"

    # Ban from the admin panel
    await a.press(Adm(s="usr", id=510).pack())
    await a.click("⛔ Ограничить доступ")
    await a.send("Нарушение правил")
    async with sm() as s:
        assert (await s.get(User, 510, populate_existing=True)).is_banned


async def test_admin_payment_check_and_broadcast(env, sm):
    c = client(env, 511)
    await c.send("/start")
    await c.click("💎 Пополнить баланс")
    await c.click("500 ₽")
    async with sm() as s:
        payment = await s.scalar(select(Payment))
    a = client(env, ADMIN_ID, "admin")
    await a.send("/admin")
    await a.press(Adm(s="pay", id=payment.id).pack())
    assert payment.uid in a.screen
    await a.click("🔄 Проверить статус")
    async with sm() as s:
        assert (await s.get(Payment, payment.id)).status == PaymentStatus.PENDING

    await a.press(Adm(s="bc").pack())
    await a.click("✍️ Новая рассылка")
    await a.send("Hello everyone")
    assert "Отправить рассылку" in a.screen
    await a.click("🚀 Отправить")
    assert "Рассылка #" in a.screen
    import asyncio

    from handlers.admin.broadcast import _tasks

    await asyncio.gather(*_tasks)
    assert "Рассылка #" in a.screen and "завершена" in a.screen
    await a.click("📊 Подробнее")
    assert "✅ завершена" in a.screen and "Доставлено: " in a.screen


async def test_commands_interrupt_admin_forms(env, sm):
    await make_product(sm, title="Form item")
    a = client(env, ADMIN_ID, "admin")
    await a.send("/admin")
    await a.press(Adm(s="pnew").pack())
    await a.click("Cat Form item")
    await a.send("/start")
    assert "Добро пожаловать" in a.screen
    await a.send("Should not become a product")
    async with sm() as s:
        assert await s.scalar(select(func.count(Product.id))) == 1
