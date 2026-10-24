"""Bot handlers driven through the real aiogram dispatcher with a fake Bot API session."""

from __future__ import annotations

from aiogram.methods import SendMessage
from aiogram.types import User
from sqlalchemy import select

from starshop.database.enums import BotButtonAction, ButtonStyle
from starshop.database.models import AdminLoginToken, BotButton, Referral, SupportTicket
from tests.botkit import USER  # noqa: F401 - used by other modules through this one
from tests.conftest import get_user, make_admin, set_runtime


async def test_start_shows_menu_and_registers_user(bot_env, session):
    calls, send, _ = bot_env
    await send("/start")
    text = calls.texts()[-1]
    assert "Анна" in text and "DEMO" in text
    assert calls.last_markup_texts() == [
        "🌐 Открыть магазин",
        "⭐️ Купить Stars",
        "👤 Профиль",
        "🧾 Мои заказы",
        "🎁 Рефералы",
        "💬 Поддержка",
    ]
    sent = [m for m in calls.calls if isinstance(m, SendMessage)][-1]
    rows = sent.reply_markup.inline_keyboard
    # Exactly one Mini App button; colours by meaning (blue — open, green — buy).
    web_apps = [b for row in rows for b in row if b.web_app]
    assert len(web_apps) == 1 and web_apps[0].web_app.url == "https://shop.test/" and web_apps[0].style == "primary"
    assert rows[1][0].style == "success" and rows[1][0].callback_data == "buy:start"
    user = await get_user(session, 777)
    assert user.bot_started and user.username == "anna_buyer"


async def test_admin_buttons_appear_in_menu_without_restart(bot_env, session, product):
    calls, send, press = bot_env
    session.add_all(
        [
            BotButton(title="Новости", emoji="📣", action=BotButtonAction.message, text="Скидки <b>в пятницу</b>", row=0, position=1),
            BotButton(title="Канал", action=BotButtonAction.url, url="https://t.me/durov", row=0, position=0, style=ButtonStyle.primary),
            BotButton(title="Lucky Buy", emoji="🍀", action=BotButtonAction.webapp, url="/lucky", row=1),
            BotButton(title="Пакет", action=BotButtonAction.product, product_id=product.id, row=2),
            BotButton(title="Скрытая", action=BotButtonAction.section, section="profile", row=2, is_active=False),
        ]
    )
    await session.commit()
    await send("/start")
    labels = calls.last_markup_texts()
    assert labels[-4:] == ["Канал", "📣 Новости", "🍀 Lucky Buy", "Пакет"] and "Скрытая" not in labels
    news = (await session.execute(select(BotButton).where(BotButton.title == "Новости"))).scalar_one()
    await press(f"cb:{news.id}")
    assert calls.texts()[-1] == "Скидки &lt;b&gt;в пятницу&lt;/b&gt;"  # admin text is shown as plain text
    pkg = (await session.execute(select(BotButton).where(BotButton.title == "Пакет"))).scalar_one()
    await press(f"cb:{pkg.id}")
    assert "100 Stars" in calls.texts()[-1] and "⭐️ Купить этот пакет" in calls.last_markup_texts()


async def test_start_with_referral_code(bot_env, session):
    _, send, _ = bot_env
    await set_runtime(session, "referral", enabled=True)
    inviter = User(id=1001, is_bot=False, first_name="Inviter")
    await send("/start", user=inviter)
    code = (await get_user(session, 1001)).referral_code
    await send(f"/start ref_{code}")
    ref = (await session.execute(select(Referral))).scalar_one()
    assert ref.referrer_id == (await get_user(session, 1001)).id


async def test_profile_orders_and_referral_screens(bot_env, session):
    calls, send, press = bot_env
    await send("/start")
    await press("menu:profile")
    assert "Telegram ID: <code>777</code>" in calls.texts()[-1]
    await press("menu:orders")
    assert "Заказов пока нет" in calls.texts()[-1]
    await press("menu:referrals")
    text = calls.texts()[-1]
    code = (await get_user(session, 777)).referral_code
    assert "Реферальная программа" in text and f"https://t.me/pulsar_test_bot?start=ref_{code}" in text
    assert "Приглашено: <b>0</b> · активировано: <b>0</b>" in text
    assert "📤 Поделиться ссылкой" in calls.last_markup_texts()
    await set_runtime(session, "referral", enabled=False)
    await press("menu:referrals")
    assert "не активна" in calls.texts()[-1]


async def test_support_flow_creates_ticket(bot_env, session):
    calls, send, press = bot_env
    await send("/start")
    await press("menu:support")
    await send("Не пришли звёзды по заказу")
    assert "обращение" in calls.texts()[-1]
    ticket = (await session.execute(select(SupportTicket))).scalar_one()
    assert ticket.subject.startswith("Не пришли звёзды")
    # Commands still work while the support prompt is open
    await press("menu:support")
    await send("/start")
    assert "Анна" in calls.texts()[-1]


async def test_admin_command(bot_env, session):
    calls, send, _ = bot_env
    await send("/admin")
    assert "Ваш Telegram ID: <code>777</code>" in calls.texts()[-1] and "ADMIN_TELEGRAM_IDS" in calls.texts()[-1]
    await make_admin(session, telegram_id=777)
    await send("/admin")
    assert "Ссылка для входа" in calls.texts()[-1]
    assert "🔐 Войти в админ-панель" in calls.last_markup_texts()
    await session.commit()
    assert (await session.execute(select(AdminLoginToken))).scalar_one().used_at is None
