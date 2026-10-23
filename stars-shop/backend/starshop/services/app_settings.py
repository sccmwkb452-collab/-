"""Runtime settings and content editable from the admin panel.

Each key of ``app_settings`` holds one JSON document validated by a pydantic
model below. Stored values are merged over the defaults, so adding a new field
later never breaks existing rows. Nothing secret is stored here: tokens and
provider keys stay in the environment.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.models import AppSetting

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"


class BrandSettings(BaseModel):
    name: str = Field(default_factory=lambda: get_settings().brand_name, max_length=40)
    tagline: str = Field(default_factory=lambda: get_settings().brand_tagline, max_length=120)
    logo_url: str | None = Field(default=None, max_length=500)
    accent_primary: str = Field(default="#2F6BFF", pattern=HEX_COLOR)
    accent_secondary: str = Field(default="#8B5CF6", pattern=HEX_COLOR)
    accent_tertiary: str = Field(default="#22D3EE", pattern=HEX_COLOR)


class HeroContent(BaseModel):
    eyebrow: str = "Telegram Stars"
    title: str = "Твои звёзды. Твои возможности."
    subtitle: str = "Пополняй Telegram Stars для себя или в подарок другу за пару касаний — без лишних шагов и скрытых наценок."
    cta_label: str = "Купить звёзды"
    benefits: list[str] = Field(
        default_factory=lambda: ["Удобная оплата", "Прозрачная цена", "Статус заказа онлайн"],
        max_length=4,
    )


class InfoItem(BaseModel):
    icon: str = "sparkles"
    title: str = Field(max_length=80)
    text: str = Field(max_length=400)


class FaqItem(BaseModel):
    q: str = Field(max_length=200)
    a: str = Field(max_length=2000)


class SupportContent(BaseModel):
    telegram: str = Field(default_factory=lambda: get_settings().support_telegram, max_length=64)
    email: str = Field(default_factory=lambda: get_settings().support_email, max_length=120)
    hours: str = "Ежедневно, 10:00–22:00 (МСК)"
    response_time: str = "Обычно отвечаем в течение 30 минут"


class LegalContent(BaseModel):
    terms: str = (
        "1. Сервис помогает оформить покупку Telegram Stars для указанного аккаунта Telegram.\n"
        "2. Перед оплатой проверьте получателя и количество звёзд — после доставки заказ нельзя изменить.\n"
        "3. Заказ считается выполненным, когда звёзды зачислены получателю. Статус отображается в разделе «Мои заказы».\n"
        "4. Мы не запрашиваем пароль, код входа или другие секретные данные вашего аккаунта.\n"
        "5. Lucky Buy, если он доступен: вы платите долю цены пакета за такой же шанс его получить. Результат определяет "
        "проверяемый розыгрыш сразу после подтверждения оплаты. При выигрыше пакет зачисляется на ваш аккаунт, при проигрыше "
        "оплата попытки не возвращается. Участие — только с 18 лет.\n"
        "6. Telegram и Telegram Stars — товарные знаки Telegram. Сервис не аффилирован с Telegram."
    )
    refund_policy: str = (
        "Если звёзды не были доставлены, мы вернём оплату тем же способом, которым она была внесена. "
        "Возврат оформляется после проверки заказа поддержкой. Доставленные звёзды вернуть нельзя: "
        "это ограничение Telegram."
    )
    payment_info: str = (
        "Оплата проходит на стороне платёжного провайдера. Заказ переходит в работу только после того, "
        "как провайдер подтвердит платёж нашему серверу."
    )


class Announcement(BaseModel):
    id: str = Field(max_length=32)
    text: str = Field(max_length=280)
    tone: Literal["info", "success", "warning"] = "info"
    link: str | None = Field(default=None, max_length=500)
    active: bool = True


class PromoBanner(BaseModel):
    id: str = Field(max_length=32)
    title: str = Field(max_length=80)
    subtitle: str = Field(default="", max_length=200)
    cta_label: str | None = Field(default=None, max_length=40)
    link: str | None = Field(default=None, max_length=500)
    accent: str = Field(default="#8B5CF6", pattern=HEX_COLOR)
    active: bool = True


class ContentSettings(BaseModel):
    hero: HeroContent = Field(default_factory=HeroContent)
    catalog_title: str = "Выбери пакет"
    catalog_subtitle: str = "Цена фиксируется в момент оформления заказа"
    how_it_works: list[InfoItem] = Field(
        default_factory=lambda: [
            InfoItem(icon="package", title="Выбери пакет", text="Готовый пакет или своё количество звёзд."),
            InfoItem(icon="user", title="Укажи получателя", text="Себе или другу по @username в Telegram."),
            InfoItem(icon="check", title="Оплати и получи", text="После подтверждения оплаты звёзды отправляются получателю."),
        ],
        max_length=6,
    )
    why_us: list[InfoItem] = Field(
        default_factory=lambda: [
            InfoItem(icon="receipt", title="Цена без сюрпризов", text="Итоговая сумма видна до оплаты: стоимость, комиссия и скидка."),
            InfoItem(
                icon="activity", title="Статус в реальном времени", text="Каждый шаг заказа отображается в приложении и приходит в чат."
            ),
            InfoItem(
                icon="shield", title="Без доступа к аккаунту", text="Нужен только @username получателя. Пароли и коды мы не запрашиваем."
            ),
            InfoItem(icon="life-buoy", title="Живая поддержка", text="Если что-то пошло не так — напишите нам прямо из приложения."),
        ],
        max_length=8,
    )
    faq: list[FaqItem] = Field(
        default_factory=lambda: [
            FaqItem(
                q="Что такое Telegram Stars?",
                a="Внутренняя валюта Telegram: ими оплачивают цифровые товары в ботах и мини-приложениях, дарят подарки и поддерживают авторов.",
            ),
            FaqItem(
                q="Как быстро приходят звёзды?",
                a="Заказ передаётся на доставку сразу после того, как платёжный провайдер подтвердит оплату. Текущий статус всегда виден в разделе «Мои заказы».",
            ),
            FaqItem(q="Можно купить звёзды другу?", a="Да. На шаге «Получатель» выберите «Другому пользователю» и укажите его @username."),
            FaqItem(
                q="Что нужно для получения?",
                a="Публичный @username в настройках Telegram. Пароль, код входа и другие секретные данные не нужны — никогда не сообщайте их никому.",
            ),
            FaqItem(
                q="Что если оплата прошла, а звёзд нет?",
                a="Откройте заказ и проверьте статус. Если он не меняется, напишите в поддержку из карточки заказа — мы проверим платёж и доставку.",
            ),
        ],
        max_length=30,
    )
    support: SupportContent = Field(default_factory=SupportContent)
    legal: LegalContent = Field(default_factory=LegalContent)
    announcements: list[Announcement] = Field(default_factory=list, max_length=5)
    promo_banners: list[PromoBanner] = Field(default_factory=list, max_length=5)


class ShopSettings(BaseModel):
    mode: Literal["demo", "production"] = Field(default_factory=lambda: get_settings().app_mode)
    maintenance: bool = False
    maintenance_message: str = "Проводим технические работы. Вернёмся совсем скоро."
    allow_gift_to_others: bool = True


class CheckoutSettings(BaseModel):
    # Extra fee shown to the customer per payment provider, in percent.
    provider_fee_percent: dict[str, Decimal] = Field(default_factory=dict)
    fee_fixed: Decimal = Decimal("0")
    min_payable: Decimal = Decimal("1.00")

    @field_validator("provider_fee_percent")
    @classmethod
    def _check_fees(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        for fee in value.values():
            if fee < 0 or fee > 50:
                raise ValueError("fee must be between 0 and 50 percent")
        return value

    @field_validator("fee_fixed", "min_payable")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("must be non-negative")
        return value


class ReferralSettings(BaseModel):
    enabled: bool = False
    reward_kind: Literal["percent", "fixed"] = "percent"
    reward_value: Decimal = Decimal("5")
    min_order_amount: Decimal = Decimal("0")
    # Share of an order that can be paid with bonus balance, percent.
    max_bonus_spend_percent: Decimal = Decimal("30")
    max_rewards_per_referrer: int | None = None

    @field_validator("reward_value", "max_bonus_spend_percent", "min_order_amount")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("must be non-negative")
        return value


class LuckySettings(BaseModel):
    """Lucky Buy: a share of the package price buys the same chance to receive
    the package. A paid attempt that does not win is not refunded, so it is a
    game of chance: by default it works only while the shop is in DEMO."""

    mode: Literal["off", "demo_only", "on"] = "demo_only"
    min_chance_percent: int = Field(default=5, ge=1, le=99)
    max_chance_percent: int = Field(default=80, ge=1, le=99)
    # Charged on top of the proportional price, percent. Shown to the customer.
    fee_percent: Decimal = Decimal("0")
    # Attempts per user in 24 hours (unpaid cancelled ones do not count); None — no limit.
    daily_limit: int | None = Field(default=20, ge=1, le=1000)

    @field_validator("fee_percent")
    @classmethod
    def _fee_range(cls, value: Decimal) -> Decimal:
        if value < 0 or value > 50:
            raise ValueError("fee must be between 0 and 50 percent")
        return value

    @model_validator(mode="after")
    def _chance_order(self) -> LuckySettings:
        if self.min_chance_percent > self.max_chance_percent:
            raise ValueError("min_chance_percent must not exceed max_chance_percent")
        return self


class NotificationSettings(BaseModel):
    user_notifications: bool = True
    admin_new_paid_order: bool = True
    admin_delivery_problem: bool = True
    admin_new_ticket: bool = True


SETTINGS_MODELS: dict[str, type[BaseModel]] = {
    "brand": BrandSettings,
    "content": ContentSettings,
    "shop": ShopSettings,
    "checkout": CheckoutSettings,
    "referral": ReferralSettings,
    "lucky": LuckySettings,
    "notifications": NotificationSettings,
}


class RuntimeSettings(BaseModel):
    brand: BrandSettings
    content: ContentSettings
    shop: ShopSettings
    checkout: CheckoutSettings
    referral: ReferralSettings
    lucky: LuckySettings
    notifications: NotificationSettings

    @property
    def lucky_available(self) -> bool:
        return self.lucky.mode == "on" or (self.lucky.mode == "demo_only" and self.shop.mode == "demo")


async def load_runtime_settings(session: AsyncSession) -> RuntimeSettings:
    rows = (await session.execute(select(AppSetting))).scalars().all()
    stored = {row.key: row.value for row in rows}
    values: dict[str, Any] = {}
    for key, model in SETTINGS_MODELS.items():
        raw = stored.get(key) or {}
        try:
            values[key] = model.model_validate(raw)
        except ValueError:
            # A broken stored value must never take the shop down.
            values[key] = model()
    return RuntimeSettings(**values)


async def save_setting(session: AsyncSession, key: str, value: dict[str, Any], admin_id: int | None) -> BaseModel:
    model = SETTINGS_MODELS[key]
    validated = model.model_validate(value)
    payload = validated.model_dump(mode="json")
    stmt = insert(AppSetting).values(key=key, value=payload, updated_by=admin_id)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AppSetting.key], set_={"value": payload, "updated_by": admin_id, "updated_at": func.now()}
    )
    await session.execute(stmt)
    return validated
