"""Server-side price calculation. The client only ever *displays* numbers
returned from here; order totals are always recomputed on the server."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import ProductKind
from ..database.models import Product, PromoCode, User
from ..delivery.base import DeliveryProvider
from ..shared.errors import NotFound, ValidationFailed
from ..shared.money import ZERO, money, percent_of
from . import lucky
from . import promo as promo_service
from .app_settings import RuntimeSettings

RATE_QUANTUM = Decimal("0.0001")


@dataclass(slots=True)
class Quote:
    product: Product
    stars_amount: int
    unit_price: Decimal
    subtotal: Decimal
    discount: Decimal
    bonus_spent: Decimal
    bonus_available: Decimal
    fee: Decimal
    total: Decimal
    currency: str
    cost_amount: Decimal | None
    promo: PromoCode | None
    promo_error: dict | None


@dataclass(slots=True)
class LuckyQuote:
    product: Product
    stars_amount: int
    unit_price: Decimal
    prize_value: Decimal
    prize_cost: Decimal | None
    chance_bp: int
    subtotal: Decimal  # the price of the attempt
    fee: Decimal
    total: Decimal
    currency: str


async def load_product(session: AsyncSession, product_id: int, *, lock: bool = False) -> Product:
    stmt = select(Product).where(Product.id == product_id, Product.is_archived.is_(False), Product.is_active.is_(True))
    if lock:
        stmt = stmt.with_for_update()
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise NotFound("Пакет недоступен", code="product_unavailable")
    return product


def stars_for(product: Product, requested: int | None, delivery: DeliveryProvider) -> int:
    if product.kind == ProductKind.package:
        stars = int(product.stars_amount or 0)
    else:
        if requested is None:
            raise ValidationFailed("Укажите количество звёзд", code="stars_required")
        stars = int(requested)
        low = max(product.min_stars or 1, delivery.min_stars)
        high = min(product.max_stars or delivery.max_stars, delivery.max_stars)
        if stars < low or stars > high:
            raise ValidationFailed(
                f"Количество звёзд должно быть от {low} до {high}",
                code="stars_out_of_range",
                details={"min": low, "max": high},
            )
    if stars < delivery.min_stars or stars > delivery.max_stars:
        raise ValidationFailed(
            f"Способ доставки поддерживает от {delivery.min_stars} до {delivery.max_stars} звёзд",
            code="stars_out_of_range",
            details={"min": delivery.min_stars, "max": delivery.max_stars},
        )
    return stars


def subtotal_for(product: Product, stars: int) -> Decimal:
    if product.kind == ProductKind.package:
        return money(product.price or 0)
    return money(Decimal(product.price_per_star or 0) * stars)


async def build_quote(
    session: AsyncSession,
    *,
    user: User,
    product: Product,
    stars_requested: int | None,
    promo_code: str | None,
    use_bonus: bool,
    payment_provider: str,
    delivery: DeliveryProvider,
    runtime: RuntimeSettings,
    strict_promo: bool,
    lock_promo: bool = False,
) -> Quote:
    """``strict_promo`` raises on an invalid promo (order creation); otherwise
    the problem is returned in ``promo_error`` (live preview)."""
    stars = stars_for(product, stars_requested, delivery)
    subtotal = subtotal_for(product, stars)
    min_payable = money(runtime.checkout.min_payable)

    promo: PromoCode | None = None
    promo_error: dict | None = None
    discount = ZERO
    if promo_code and promo_code.strip():
        try:
            promo = await promo_service.validate(session, promo_code, user, subtotal, lock=lock_promo)
            discount = promo_service.compute_discount(promo, subtotal)
        except ValidationFailed as exc:
            if strict_promo:
                raise
            promo_error = {"code": exc.code, "message": exc.message}
    discount = min(discount, max(ZERO, subtotal - min_payable))

    bonus_available = money(user.bonus_balance)
    bonus_spent = ZERO
    if use_bonus and runtime.referral.enabled and bonus_available > 0:
        cap = percent_of(subtotal - discount, runtime.referral.max_bonus_spend_percent)
        bonus_spent = min(bonus_available, cap, max(ZERO, subtotal - discount - min_payable))

    base = subtotal - discount - bonus_spent
    fee_percent = runtime.checkout.provider_fee_percent.get(payment_provider, Decimal("0"))
    fee = money(percent_of(base, fee_percent) + money(runtime.checkout.fee_fixed)) if base > 0 else ZERO
    total = money(base + fee)

    cost_amount = money(Decimal(product.cost_per_star) * stars) if product.cost_per_star is not None else None
    unit_price = (subtotal / stars).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
    return Quote(
        product=product,
        stars_amount=stars,
        unit_price=unit_price,
        subtotal=subtotal,
        discount=money(discount),
        bonus_spent=money(bonus_spent),
        bonus_available=bonus_available,
        fee=fee,
        total=total,
        currency=get_settings().shop_currency,
        cost_amount=cost_amount,
        promo=promo,
        promo_error=promo_error,
    )


def build_lucky_quote(
    *, product: Product, chance_percent: int, payment_provider: str, delivery: DeliveryProvider, runtime: RuntimeSettings
) -> LuckyQuote:
    """Lucky Buy attempt: promo codes and bonuses do not apply."""
    if product.kind != ProductKind.package:
        raise ValidationFailed("Lucky Buy доступен для готовых пакетов", code="lucky_package_only")
    stars = stars_for(product, None, delivery)
    prize_value = subtotal_for(product, stars)
    bp = lucky.chance_bp(chance_percent, runtime)
    stake = lucky.stake_for(prize_value, bp, runtime.lucky.fee_percent)
    min_payable = money(runtime.checkout.min_payable)
    if stake < min_payable:
        raise ValidationFailed("Слишком маленькая сумма попытки: увеличьте шанс или выберите пакет побольше", code="lucky_stake_too_small")
    fee_percent = runtime.checkout.provider_fee_percent.get(payment_provider, Decimal("0"))
    fee = money(percent_of(stake, fee_percent) + money(runtime.checkout.fee_fixed))
    return LuckyQuote(
        product=product,
        stars_amount=stars,
        unit_price=(prize_value / stars).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP),
        prize_value=prize_value,
        prize_cost=money(Decimal(product.cost_per_star) * stars) if product.cost_per_star is not None else None,
        chance_bp=bp,
        subtotal=stake,
        fee=fee,
        total=money(stake + fee),
        currency=get_settings().shop_currency,
    )
