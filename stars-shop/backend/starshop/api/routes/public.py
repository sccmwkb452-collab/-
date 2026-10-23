from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select, text

from ...config import get_settings
from ...database.models import Product
from ...delivery.registry import get_delivery_provider
from ...payments.registry import enabled_providers
from ...services.app_settings import RuntimeSettings
from ..deps import RuntimeDep, SessionDep
from ..ratelimit import get_limiter
from ..serializers import product_public

router = APIRouter()
health_router = APIRouter()


async def active_products(session) -> list[Product]:
    rows = await session.execute(
        select(Product).where(Product.is_archived.is_(False), Product.is_active.is_(True)).order_by(Product.sort_order, Product.id)
    )
    return list(rows.scalars())


def public_config(runtime: RuntimeSettings) -> dict:
    settings = get_settings()
    delivery = get_delivery_provider()
    fees = runtime.checkout.provider_fee_percent
    content = runtime.content.model_dump(mode="json")
    content["announcements"] = [a for a in content["announcements"] if a["active"]]
    content["promo_banners"] = [b for b in content["promo_banners"] if b["active"]]
    return {
        "brand": runtime.brand.model_dump(mode="json"),
        "mode": runtime.shop.mode,
        "maintenance": {"enabled": runtime.shop.maintenance, "message": runtime.shop.maintenance_message},
        "currency": settings.shop_currency,
        "timezone": settings.display_timezone,
        "content": content,
        "payment_methods": [
            {"id": p.name, "title": p.title, "description": p.description, "is_demo": p.is_demo, "fee_percent": str(fees.get(p.name, 0))}
            for p in enabled_providers(runtime.shop.mode)
        ],
        "delivery": {
            "provider": delivery.name,
            "is_demo": delivery.is_demo,
            "min_stars": delivery.min_stars,
            "max_stars": delivery.max_stars,
            "gifts_enabled": runtime.shop.allow_gift_to_others and delivery.supports_gift_to_others,
            "requires_username": delivery.requires_username,
        },
        "referral": {"enabled": runtime.referral.enabled, "max_bonus_spend_percent": str(runtime.referral.max_bonus_spend_percent)},
        "bot_username": settings.bot_username or None,
    }


@router.get("/bootstrap")
async def bootstrap(session: SessionDep, runtime: RuntimeDep) -> dict:
    """Everything the Mini App needs for the first paint, in one request."""
    data = public_config(runtime)
    data["catalog"] = [product_public(p) for p in await active_products(session)]
    return data


@router.get("/catalog")
async def catalog(session: SessionDep) -> dict:
    return {"items": [product_public(p) for p in await active_products(session)]}


@health_router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@health_router.get("/health/ready")
async def ready(session: SessionDep) -> dict:
    await session.execute(text("SELECT 1"))
    redis = await get_limiter().ping()
    return {"status": "ok", "database": True, "redis": redis}
