"""Request bodies. Responses are built by ``serializers``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..database.enums import AdminRole, ProductKind, PromoKind


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecipientIn(Strict):
    type: Literal["self", "username"] = "self"
    username: str | None = Field(default=None, max_length=64)


class LuckyIn(Strict):
    # Chance to win, whole percent; the allowed range is a runtime setting.
    chance: int = Field(ge=1, le=99)


class QuoteIn(Strict):
    product_id: int
    stars_amount: int | None = Field(default=None, ge=1, le=10_000_000)
    promo_code: str | None = Field(default=None, max_length=32)
    use_bonus: bool = False
    payment_provider: str = Field(max_length=32)
    lucky: LuckyIn | None = None


class OrderIn(QuoteIn):
    recipient: RecipientIn


class PaymentIn(Strict):
    provider: str | None = Field(default=None, max_length=32)
    # Lucky Buy: the customer's seed for the provably fair draw (fixed by the first payment).
    client_seed: str | None = Field(default=None, max_length=64)


class RecipientCheckIn(Strict):
    username: str = Field(max_length=64)
    # The product decides the delivery channel (Telegram Premium can have its own).
    product_id: int | None = None


class TicketIn(Strict):
    text: str = Field(min_length=1, max_length=4000)
    subject: str | None = Field(default=None, max_length=160)
    order_id: str | None = None


class MessageIn(Strict):
    text: str = Field(min_length=1, max_length=4000)


class DemoCompleteIn(Strict):
    outcome: Literal["success", "fail"] = "success"


# --- admin ---------------------------------------------------------------------


class LoginTokenIn(Strict):
    token: str = Field(min_length=20, max_length=128)


class InitDataIn(Strict):
    init_data: str = Field(min_length=10, max_length=8192)


class LoginWidgetIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    auth_date: int
    hash: str


class ProductIn(Strict):
    kind: ProductKind = ProductKind.package
    title: str | None = Field(default=None, max_length=64)
    badge: str | None = Field(default=None, max_length=32)
    stars_amount: int | None = Field(default=None, ge=1, le=10_000_000)
    price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    price_per_star: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)
    min_stars: int | None = Field(default=None, ge=1)
    max_stars: int | None = Field(default=None, ge=1)
    cost_per_star: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    premium_months: Literal[3, 6, 12] | None = None
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    cost_source: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    is_popular: bool = False
    sort_order: int = 0


class ProductPatch(Strict):
    title: str | None = Field(default=None, max_length=64)
    badge: str | None = Field(default=None, max_length=32)
    stars_amount: int | None = Field(default=None, ge=1, le=10_000_000)
    price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    price_per_star: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)
    min_stars: int | None = Field(default=None, ge=1)
    max_stars: int | None = Field(default=None, ge=1)
    cost_per_star: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    premium_months: Literal[3, 6, 12] | None = None
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    cost_source: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_popular: bool | None = None
    sort_order: int | None = None


class ReorderIn(Strict):
    ids: list[int] = Field(min_length=1, max_length=200)


class ReasonIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class RefundIn(ReasonIn):
    allow_completed: bool = False


class RetryIn(Strict):
    confirm_not_delivered: bool = False


class ReferenceIn(Strict):
    reference: str = Field(min_length=4, max_length=128)
    note: str | None = Field(default=None, max_length=500)


class NoteIn(Strict):
    text: str = Field(min_length=1, max_length=2000)


class BlockIn(Strict):
    reason: str = Field(min_length=3, max_length=500)


class PromoIn(Strict):
    code: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=255)
    kind: PromoKind
    value: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    max_discount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    min_order_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    per_user_limit: int = Field(default=1, ge=1, le=1000)
    first_order_only: bool = False
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class PromoPatch(Strict):
    description: str | None = Field(default=None, max_length=255)
    max_discount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    min_order_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    max_uses: int | None = Field(default=None, ge=1)
    per_user_limit: int | None = Field(default=None, ge=1, le=1000)
    first_order_only: bool | None = None
    is_active: bool | None = None


class AdminIn(Strict):
    telegram_id: int = Field(gt=0)
    username: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, max_length=128)
    role: AdminRole = AdminRole.support


class AdminPatch(Strict):
    display_name: str | None = Field(default=None, max_length=128)
    role: AdminRole | None = None
    is_active: bool | None = None


class ReplyIn(Strict):
    text: str = Field(min_length=1, max_length=4000)


class WithdrawalIn(Strict):
    stars: int = Field(ge=1, le=10_000_000)


class WithdrawalRejectIn(Strict):
    comment: str = Field(min_length=3, max_length=255)
