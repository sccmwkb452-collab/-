"""
Текстовые шаблоны интерфейса в тёмном премиальном стиле.

Правила оформления:
  ◆  Заголовки — крупные, жирные, с декоративным emoji
  ◆  Разделители — ─────────────────────────────
  ◆  Списки — через › или ▸
  ◆  «Золотые» акценты — bold + ✦ / ◆
  ◆  Пустые состояния — мягкие, с призывом к действию
"""
from __future__ import annotations

from datetime import datetime

from bot.ui.rich_text import RichTextBuilder, e
from database.models.subscription import Subscription, SubscriptionPlan
from database.models.user import User


# ─────────────────────────────────────────────────────────────────────────────
#  Главный экран
# ─────────────────────────────────────────────────────────────────────────────

def welcome_new(user: User) -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("shield").text(" ").bold("NFT Gift Bot").newline()
    rt.separator("─", 26).newline(2)
    rt.text("Привет, ").bold(user.full_name).text("!").newline(2)
    rt.italic("Добро пожаловать в мир цифровых подарков.").newline(2)
    rt.text(f"{e('diamond')} Покупай эксклюзивные NFT-подарки").newline()
    rt.text(f"{e('gift')} Дари их прямо в Telegram").newline()
    rt.text(f"{e('crown')} Управляй коллекцией с Premium-подпиской").newline(2)
    rt.separator("─", 26).newline()
    rt.italic("Выбери раздел:")
    return rt.build()


def welcome_back(user: User) -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("shield").text(" ").bold("NFT Gift Bot").newline()
    rt.separator("─", 26).newline(2)
    rt.text("С возвращением, ").bold(user.full_name).text("!").newline(2)
    rt.separator("─", 26).newline()
    rt.italic("Выбери раздел:")
    return rt.build()


# ─────────────────────────────────────────────────────────────────────────────
#  Подписка
# ─────────────────────────────────────────────────────────────────────────────

PLAN_LABELS = {
    SubscriptionPlan.BASIC: "Basic",
    SubscriptionPlan.PREMIUM: "Premium",
}

PLAN_FEATURES = {
    SubscriptionPlan.BASIC: [
        "До 10 NFT-подарков в коллекции",
        "Базовое управление подарками",
        "История операций (30 дней)",
    ],
    SubscriptionPlan.PREMIUM: [
        "Неограниченная коллекция NFT",
        "Передача подарков другим пользователям",
        "Приоритетная поддержка 24/7",
        "Ранний доступ к новым функциям",
        "История операций (∞)",
    ],
}


def subscription_plans(
    basic_stars: int,
    premium_stars: int,
    basic_days: int,
    premium_days: int,
) -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("diamond").text(" ").bold("Подписки").newline()
    rt.separator("─", 26).newline(2)

    # Basic
    rt.bold(f"▸ {e('gem_blue')} Basic — {basic_stars} ⭐ / {basic_days} дней").newline()
    for feat in PLAN_FEATURES[SubscriptionPlan.BASIC]:
        rt.text(f"  › {feat}").newline()
    rt.newline()

    # Premium
    rt.bold(f"▸ {e('crown')} Premium — {premium_stars} ⭐ / {premium_days} дней").newline()
    for feat in PLAN_FEATURES[SubscriptionPlan.PREMIUM]:
        rt.text(f"  › {feat}").newline()
    rt.newline()

    rt.separator("─", 26).newline()
    rt.italic(f"{e('star')} Оплата — Telegram Stars (XTR). Звёзды можно купить в настройках Telegram.")
    return rt.build()


def subscription_active(sub: Subscription) -> tuple[str, list]:
    label = PLAN_LABELS.get(sub.plan, sub.plan.value.title())
    expires = sub.expires_at.strftime("%d.%m.%Y") if sub.expires_at else "Бессрочно"

    rt = RichTextBuilder()
    rt.custom_emoji("diamond").text(" ").bold("Моя подписка").newline()
    rt.separator("─", 26).newline(2)
    rt.text(f"{e('check')} Статус: ").bold("Активна").newline()
    rt.text(f"{e('crown')} План: ").bold(label).newline()
    rt.text(f"{e('calendar')} Действует до: ").bold(expires).newline(2)
    rt.separator("─", 26).newline()
    rt.italic("Все возможности разблокированы.")
    return rt.build()


def subscription_none() -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("diamond").text(" ").bold("Подписка").newline()
    rt.separator("─", 26).newline(2)
    rt.text(f"{e('cross')} Активная подписка не найдена.").newline(2)
    rt.italic("Выбери план ниже, чтобы разблокировать полный доступ:")
    return rt.build()


# ─────────────────────────────────────────────────────────────────────────────
#  NFT-подарки
# ─────────────────────────────────────────────────────────────────────────────

def gifts_empty() -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("gift").text(" ").bold("Мои подарки").newline()
    rt.separator("─", 26).newline(2)
    rt.text(f"{e('nft')} Твоя коллекция пуста.").newline(2)
    rt.italic("Здесь будут отображаться все полученные\nи купленные NFT-подарки.")
    return rt.build()


def gifts_list_header(count: int) -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("gift").text(" ").bold("Мои подарки").newline()
    rt.separator("─", 26).newline(2)
    rt.text(f"{e('nft')} В коллекции: ").bold(f"{count} подарков").newline(2)
    rt.italic("Выбери подарок для просмотра деталей:")
    return rt.build()


# ─────────────────────────────────────────────────────────────────────────────
#  Подключить аккаунт
# ─────────────────────────────────────────────────────────────────────────────

def connect_account_info() -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("link").text(" ").bold("Подключить аккаунт").newline()
    rt.separator("─", 26).newline(2)
    rt.bold("Зачем подключать аккаунт?").newline(2)
    rt.text(f"{e('gift')} Принимать NFT-подарки на аккаунт").newline()
    rt.text(f"{e('arrow_right')} Передавать подарки через Business Bot API").newline()
    rt.text(f"{e('shield')} Безопасное управление коллекцией").newline(2)
    rt.separator("─", 26).newline(2)
    rt.bold("Как подключить:").newline(2)
    rt.text(f"1️⃣ Открой ").bold("Настройки Telegram").text(" › ").bold("Telegram Business").newline()
    rt.text(f"2️⃣ Выбери ").bold("Чат-боты").text(" › добавь этого бота").newline()
    rt.text(f"3️⃣ Нажми ").bold("Подтвердить").text(" — аккаунт будет связан").newline(2)
    rt.separator("─", 26).newline()
    rt.italic(f"{e('warning')} Требуется Telegram Business (Premium).")
    return rt.build()


# ─────────────────────────────────────────────────────────────────────────────
#  Tdata
# ─────────────────────────────────────────────────────────────────────────────

def tdata_shop_info() -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("cart").text(" ").bold("Купить Tdata").newline()
    rt.separator("─", 26).newline(2)
    rt.bold("Что такое Tdata?").newline(2)
    rt.text("Tdata — файл сессии Telegram-аккаунта, ").newline()
    rt.text("позволяющий войти без номера телефона.").newline(2)
    rt.separator("─", 26).newline(2)
    rt.text(f"{e('warning')} ").bold("Важно:").newline()
    rt.text("› Используй только для законных целей.").newline()
    rt.text("› Покупка аккаунтов нарушает ToS Telegram.").newline()
    rt.text("› Мы не несём ответственности за блокировки.").newline(2)
    rt.separator("─", 26).newline()
    rt.italic("Раздел находится в разработке. Скоро будет каталог.")
    return rt.build()


# ─────────────────────────────────────────────────────────────────────────────
#  Профиль
# ─────────────────────────────────────────────────────────────────────────────

def profile(
    user: User,
    sub: "Subscription | None",
    gift_count: int,
    tx_count: int,
) -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("profile").text(" ").bold("Профиль").newline()
    rt.separator("─", 26).newline(2)
    rt.text(f"{e('sparkle')} ").bold(user.full_name).newline()
    rt.text(f"  ID: ").code(str(user.telegram_id)).newline()
    if user.username:
        rt.text(f"  Username: @{user.username}").newline()
    rt.text(f"  Регистрация: {user.created_at.strftime('%d.%m.%Y')}").newline(2)

    rt.separator("─", 26).newline(2)

    if sub and sub.is_active:
        from database.models.subscription import SubscriptionPlan
        label = PLAN_LABELS.get(sub.plan, sub.plan.value)
        expires = sub.expires_at.strftime("%d.%m.%Y") if sub.expires_at else "∞"
        rt.text(f"{e('crown')} Подписка: ").bold(f"{label}").text(f" (до {expires})").newline()
    else:
        rt.text(f"{e('lock')} Подписка: ").italic("нет").newline()

    rt.text(f"{e('gift')} NFT-подарков: ").bold(str(gift_count)).newline()
    rt.text(f"{e('stats')} Операций: ").bold(str(tx_count)).newline()
    return rt.build()


# ─────────────────────────────────────────────────────────────────────────────
#  Информация и поддержка
# ─────────────────────────────────────────────────────────────────────────────

def info_and_support(support_username: str) -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.custom_emoji("info").text(" ").bold("Информация и поддержка").newline()
    rt.separator("─", 26).newline(2)
    rt.bold("О боте:").newline(2)
    rt.text(f"{e('shield')} NFT Gift Bot — сервис управления").newline()
    rt.text("NFT-подарками Telegram с Premium-подпиской.").newline(2)
    rt.bold("Возможности:").newline()
    rt.text(f"› {e('gift')} Покупка и хранение NFT-подарков").newline()
    rt.text(f"› {e('diamond')} Управление подпиской").newline()
    rt.text(f"› {e('rocket')} Передача подарков другим пользователям").newline(2)
    rt.separator("─", 26).newline(2)
    rt.bold("Поддержка:").newline(2)
    rt.text(f"{e('support')} Написать: @{support_username}").newline()
    rt.text(f"{e('calendar')} Время ответа: до 24 часов").newline(2)
    rt.separator("─", 26).newline()
    rt.italic(f"Твой ID: ")
    return rt.build()  # caller appends user ID as code entity
