"""Lucky Buy: a share of a package's price buys the same chance to receive it.

Provably fair, commit-reveal:

1. When the order is created the server picks ``server_seed`` (32 random
   bytes, hex) and publishes ``server_seed_hash = sha256(server_seed)``.
2. When the first payment is created the customer's app sends ``client_seed``.
   It is chosen after the hash is known and never changes afterwards.
3. The draw runs once, in the transaction that confirms the payment::

       digest  = HMAC-SHA256(key=server_seed, msg=f"{client_seed}:{order_number}")
       roll_bp = (first 8 bytes of digest, big-endian) * 10000 >> 64   # 0…9999
       won     = roll_bp < chance_bp

4. ``server_seed`` is revealed only after the draw, so anyone can recompute it.

The server cannot pick a seed against the customer (its hash is fixed before
the client seed exists), and nobody can know the outcome before paying. The
seed of an unpaid order stays secret too: a late payment could still revive it.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ActorType, OrderKind, OrderStatus, ProductKind
from ..database.models import LuckyDraw, Order, Product, User
from ..shared.errors import Conflict, ServiceUnavailable, ValidationFailed
from ..shared.timeutil import utcnow
from .app_settings import RuntimeSettings
from .state_machine import add_event

BP = 10_000
CURRENCY = "XTR"  # attempts are paid in Telegram Stars
CLIENT_SEED_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def new_server_seed() -> str:
    return secrets.token_hex(32)


def seed_hash(server_seed: str) -> str:
    return hashlib.sha256(server_seed.encode()).hexdigest()


def roll(server_seed: str, client_seed: str, nonce: str) -> int:
    """Uniform number 0…9999 (basis points) derived from both seeds."""
    digest = hmac.new(server_seed.encode(), f"{client_seed}:{nonce}".encode(), hashlib.sha256).digest()
    return (int.from_bytes(digest[:8], "big") * BP) >> 64


def percent_str(bp: int) -> str:
    """Chance for display: 2500 -> "25", 3750 -> "37.5"."""
    whole, frac = divmod(bp, 100)
    return str(whole) if not frac else f"{whole}.{frac:02d}".rstrip("0")


def roll_str(roll_bp: int) -> str:
    """Drawn number on the 0–100 scale: 3742 -> "37.42", 500 -> "5.00"."""
    return f"{roll_bp // 100}.{roll_bp % 100:02d}"


def ru(number: str) -> str:
    """Decimal comma for texts shown to people: "37.42" -> "37,42"."""
    return number.replace(".", ",")


def ensure_available(runtime: RuntimeSettings) -> None:
    if not runtime.lucky_available:
        raise ServiceUnavailable("Lucky Buy сейчас недоступен", code="lucky_unavailable")


def chance_bp(percent: int, runtime: RuntimeSettings) -> int:
    low, high = runtime.lucky.min_chance_percent, runtime.lucky.max_chance_percent
    if not low <= percent <= high:
        raise ValidationFailed(f"Шанс должен быть от {low} до {high}%", code="lucky_chance_out_of_range", details={"min": low, "max": high})
    return percent * 100


def stake_for(prize_stars: int, bp: int, fee_percent: Decimal) -> int:
    """Proportional share of the prize plus the Lucky Buy fee, in whole Stars (rounded up)."""
    exact = Decimal(prize_stars) * bp * (100 + Decimal(fee_percent)) / (BP * 100)
    return int(exact.to_integral_value(rounding=ROUND_CEILING))


def is_prize(product: Product, runtime: RuntimeSettings) -> bool:
    ids = runtime.lucky.prize_product_ids
    return product.kind == ProductKind.package and (not ids or product.id in ids)


async def check_daily_limit(session: AsyncSession, user: User, runtime: RuntimeSettings) -> None:
    limit = runtime.lucky.daily_limit
    if limit is None:
        return
    used = await session.scalar(
        select(func.count())
        .select_from(Order)
        .where(
            Order.user_id == user.id,
            Order.kind == OrderKind.lucky,
            Order.status != OrderStatus.cancelled,
            Order.created_at >= utcnow() - timedelta(hours=24),
        )
    )
    if (used or 0) >= limit:
        raise Conflict("Лимит попыток Lucky Buy на сутки исчерпан. Попробуйте позже", code="lucky_daily_limit", details={"limit": limit})


def new_draw(order: Order, bp: int, prize_value: Decimal, prize_cost: Decimal | None) -> LuckyDraw:
    server_seed = new_server_seed()
    return LuckyDraw(
        order_id=order.id,
        chance_bp=bp,
        prize_value=prize_value,
        prize_cost=prize_cost,
        server_seed=server_seed,
        server_seed_hash=seed_hash(server_seed),
    )


async def _lock(session: AsyncSession, order: Order) -> LuckyDraw:
    draw = (
        await session.execute(
            select(LuckyDraw).where(LuckyDraw.order_id == order.id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if draw is None:  # pragma: no cover - created together with the order
        raise Conflict("Розыгрыш для заказа не найден", code="lucky_draw_missing")
    return draw


async def fix_client_seed(session: AsyncSession, order: Order, client_seed: str | None) -> None:
    """Called when a payment is created. The first seed wins; later ones are ignored."""
    draw = await _lock(session, order)
    if draw.client_seed is not None:
        return
    if not client_seed or not CLIENT_SEED_RE.fullmatch(client_seed):
        raise ValidationFailed("Не передан сид клиента для честного розыгрыша. Обновите приложение", code="lucky_client_seed_required")
    draw.client_seed = client_seed
    add_event(session, order, "lucky_seed_fixed", actor_type=ActorType.user, public=False, data={"client_seed": client_seed})


async def draw(session: AsyncSession, order: Order) -> LuckyDraw:
    """Exactly once per order; repeated calls return the stored result."""
    lucky = await _lock(session, order)
    if lucky.drawn_at is not None:
        return lucky
    if lucky.client_seed is None:
        # Not reachable through the API (a payment needs the seed); kept so a
        # captured payment is never stuck. The event marks the draw as such.
        lucky.client_seed = secrets.token_hex(16)
        add_event(session, order, "lucky_seed_generated", public=False, message="Сид клиента сгенерирован сервером")
    lucky.roll_bp = roll(lucky.server_seed, lucky.client_seed, order.number)
    lucky.won = lucky.roll_bp < lucky.chance_bp
    lucky.drawn_at = utcnow()
    return lucky


def view(lucky: LuckyDraw, order: Order) -> dict[str, Any]:
    drawn = lucky.drawn_at is not None
    return {
        "chance": percent_str(lucky.chance_bp),
        "chance_bp": lucky.chance_bp,
        "prize_value": str(lucky.prize_value),
        "server_seed_hash": lucky.server_seed_hash,
        "client_seed": lucky.client_seed,
        "nonce": order.number,
        # Secret until the draw — see the module docstring.
        "server_seed": lucky.server_seed if drawn else None,
        "roll": roll_str(lucky.roll_bp) if drawn and lucky.roll_bp is not None else None,
        "roll_bp": lucky.roll_bp if drawn else None,
        "won": lucky.won if drawn else None,
        "drawn_at": lucky.drawn_at.isoformat() if lucky.drawn_at else None,
    }
