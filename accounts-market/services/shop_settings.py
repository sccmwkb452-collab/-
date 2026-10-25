"""Shop settings editable from the admin panel, stored in the `settings` table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Setting

DEFAULT_WELCOME = (
    "Добро пожаловать в магазин цифровых товаров!\n\n"
    "🛍 Удобный каталог\n"
    "⚡ Быстрое оформление заказа\n"
    "🔒 Безопасная обработка платежей\n\n"
    "Выберите нужный раздел ниже"
)

DEFAULT_RULES = (
    "1. В магазине продаются только товары, которые разрешено передавать и перепродавать.\n"
    "2. Данные товара выдаются сразу после оплаты и видны только покупателю.\n"
    "3. Проверьте товар в течение 24 часов после покупки. Если он не соответствует описанию, "
    "напишите в поддержку и укажите номер заказа.\n"
    "4. Средства на балансе не выводятся, их можно потратить на любые товары магазина.\n"
    "5. Запрещено использовать товары для спама, мошенничества и нарушения правил сторонних сервисов.\n"
    "6. Администрация может ограничить доступ к магазину при нарушении правил."
)


@dataclass(frozen=True)
class SettingDef:
    key: str
    title: str
    default: str
    hint: str
    validate: Callable[[str], str]
    optional: bool = False


def _text(limit: int) -> Callable[[str], str]:
    def check(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Значение не может быть пустым")
        if len(value) > limit:
            raise ValueError(f"Слишком длинно: максимум {limit} символов")
        return value

    return check


def _link(value: str) -> str:
    value = value.strip()
    if value.startswith("@") and len(value) > 1:
        return value
    if value.startswith(("https://", "http://", "tg://")):
        return value
    raise ValueError("Укажите @username или ссылку https://…")


def _percent(value: str) -> str:
    value = value.strip().replace(",", ".").rstrip("%")
    try:
        number = float(value)
    except ValueError:
        raise ValueError("Укажите число от 0 до 50") from None
    if not 0 <= number <= 50:
        raise ValueError("Процент должен быть от 0 до 50")
    return f"{number:g}"


def _rubles(value: str) -> str:
    value = value.strip().replace(" ", "").rstrip("₽")
    if not value.isdigit() or not 1 <= int(value) <= 1_000_000:
        raise ValueError("Укажите целое число рублей от 1 до 1 000 000")
    return str(int(value))


def _ref_mode(value: str) -> str:
    value = value.strip().lower()
    aliases = {"first": "first", "первая": "first", "every": "every", "каждая": "every"}
    if value not in aliases:
        raise ValueError("Допустимо: first (только первая покупка) или every (каждая покупка)")
    return aliases[value]


SETTINGS: dict[str, SettingDef] = {
    d.key: d
    for d in (
        SettingDef("shop_name", "Название магазина", "ACCOUNTS MARKET", "До 32 символов", _text(32)),
        SettingDef("welcome_text", "Приветственный текст", DEFAULT_WELCOME, "До 700 символов", _text(700)),
        SettingDef("rules_text", "Правила магазина", DEFAULT_RULES, "До 900 символов", _text(900)),
        SettingDef("news_channel", "Канал новостей", "", "@channel или https://t.me/…", _link, optional=True),
        SettingDef("support_link", "Ссылка поддержки", "", "@username или https://t.me/…", _link, optional=True),
        SettingDef("referral_percent", "Реферальный процент", "5", "Число от 0 до 50", _percent),
        SettingDef(
            "referral_mode",
            "Условие начисления",
            "every",
            "first — только с первой покупки, every — с каждой",
            _ref_mode,
        ),
        SettingDef("min_topup", "Мин. сумма пополнения, ₽", "100", "Целое число рублей", _rubles),
    )
}


@dataclass(frozen=True)
class ShopSettings:
    shop_name: str
    welcome_text: str
    rules_text: str
    news_channel: str
    support_link: str
    referral_percent: float
    referral_mode: str
    min_topup: int  # kopecks

    @property
    def support_url(self) -> str | None:
        return to_url(self.support_link)

    @property
    def news_url(self) -> str | None:
        return to_url(self.news_channel)


def to_url(link: str) -> str | None:
    if not link:
        return None
    if link.startswith("@"):
        return f"https://t.me/{link[1:]}"
    return link


async def load_raw(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(Setting.key, Setting.value))).all()
    values = {d.key: d.default for d in SETTINGS.values()}
    values.update({k: v for k, v in rows if k in SETTINGS})
    return values


async def load(session: AsyncSession) -> ShopSettings:
    raw = await load_raw(session)
    return ShopSettings(
        shop_name=raw["shop_name"],
        welcome_text=raw["welcome_text"],
        rules_text=raw["rules_text"],
        news_channel=raw["news_channel"],
        support_link=raw["support_link"],
        referral_percent=float(raw["referral_percent"]),
        referral_mode=raw["referral_mode"],
        min_topup=int(raw["min_topup"]) * 100,
    )


async def save(session: AsyncSession, key: str, value: str) -> None:
    stmt = insert(Setting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
    await session.execute(stmt)


async def ensure_defaults(session: AsyncSession, shop_name: str) -> None:
    """Writes missing settings on first start (shop name comes from SHOP_NAME)."""
    existing = set((await session.execute(select(Setting.key))).scalars())
    for d in SETTINGS.values():
        if d.key not in existing:
            value = shop_name if d.key == "shop_name" and shop_name else d.default
            await session.execute(insert(Setting).values(key=d.key, value=value).on_conflict_do_nothing())
