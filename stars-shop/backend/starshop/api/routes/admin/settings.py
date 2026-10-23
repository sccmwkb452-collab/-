from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from ....config import get_settings
from ....database.enums import AdminRole
from ....database.models import AdminUser
from ....delivery.registry import get_delivery_provider
from ....payments.registry import KNOWN_PROVIDERS, get_payment_provider
from ....services import audit
from ....services.app_settings import SETTINGS_MODELS, load_runtime_settings, save_setting
from ....shared.errors import Conflict, NotFound, ValidationFailed
from ...deps import ManagerAdmin, OwnerAdmin, SessionDep, SupportAdmin
from ...schemas import AdminIn, AdminPatch
from ...serializers import admin_user

router = APIRouter()

MANAGER_KEYS = {"brand", "content"}


def integrations() -> dict[str, Any]:
    """Configuration status only — secrets are never returned."""
    s = get_settings()
    delivery = get_delivery_provider()
    payments = []
    for name in KNOWN_PROVIDERS:
        p = get_payment_provider(name)
        payments.append(
            {
                "id": name,
                "title": p.title,
                "enabled": name in s.payment_providers,
                "configured": p.is_configured(),
                "is_demo": p.is_demo,
                "supports_refunds": p.supports_refunds,
            }
        )
    return {
        "app_env": s.app_env,
        "allow_production": s.allow_production,
        "bot": {
            "token_configured": bool(s.bot_token.get_secret_value()),
            "username": s.bot_username or None,
            "mode": s.bot_mode,
            "webapp_url": s.webapp_url,
        },
        "payments": payments,
        "cryptopay_network": s.cryptopay_network,
        "delivery": {
            "id": delivery.name,
            "title": delivery.title,
            "configured": delivery.is_configured(),
            "is_demo": delivery.is_demo,
            "idempotent": delivery.idempotent,
            "min_stars": delivery.min_stars,
            "max_stars": delivery.max_stars,
        },
        "redis_configured": bool(s.redis_url),
        "currency": s.shop_currency,
        "timezone": s.display_timezone,
        "bootstrap_admin_ids": s.admin_telegram_ids,
    }


def _check_production_allowed() -> None:
    s = get_settings()
    if not s.allow_production:
        raise ValidationFailed("PRODUCTION запрещён конфигурацией сервера (ALLOW_PRODUCTION=false)", code="production_not_allowed")
    delivery = get_delivery_provider()
    if delivery.is_demo or not delivery.is_configured():
        raise ValidationFailed(
            "Подключите реальный способ доставки (DELIVERY_PROVIDER=manual или http_supplier)", code="production_delivery_missing"
        )
    real = [
        n
        for n in s.payment_providers
        if n in KNOWN_PROVIDERS and not get_payment_provider(n).is_demo and get_payment_provider(n).is_configured()
    ]
    if not real:
        raise ValidationFailed("Подключите хотя бы один реальный платёжный провайдер", code="production_payments_missing")


@router.get("/settings")
async def get_all(ctx: SupportAdmin, session: SessionDep) -> dict:
    runtime = await load_runtime_settings(session)
    return {"settings": runtime.model_dump(mode="json"), "integrations": integrations()}


@router.put("/settings/{key}")
async def put_setting(key: str, value: dict[str, Any], ctx: ManagerAdmin, session: SessionDep) -> dict:
    if key not in SETTINGS_MODELS:
        raise NotFound("Неизвестный раздел настроек", code="unknown_setting")
    if key not in MANAGER_KEYS:
        ctx.require(AdminRole.owner)
    runtime = await load_runtime_settings(session)
    before = getattr(runtime, key).model_dump(mode="json")
    if key == "shop" and value.get("mode") == "production" and before.get("mode") != "production":
        _check_production_allowed()
    try:
        saved = await save_setting(session, key, value, ctx.admin.id)
    except ValueError as exc:
        raise ValidationFailed("Проверьте значения настроек", code="settings_invalid", details=str(exc)[:500]) from exc
    after = saved.model_dump(mode="json")
    await audit.record(
        session, ctx.admin, f"settings.{key}", entity_type="settings", entity_id=key, before=before, after=after, meta=ctx.meta
    )
    await session.commit()
    return {"key": key, "value": after}


# --- administrators -----------------------------------------------------------


@router.get("/admins")
async def list_admins(ctx: OwnerAdmin, session: SessionDep) -> dict:
    rows = (await session.execute(select(AdminUser).order_by(AdminUser.id))).scalars()
    return {"items": [admin_user(a) for a in rows]}


@router.post("/admins", status_code=201)
async def add_admin(body: AdminIn, ctx: OwnerAdmin, session: SessionDep) -> dict:
    existing = (await session.execute(select(AdminUser).where(AdminUser.telegram_id == body.telegram_id))).scalar_one_or_none()
    if existing is not None:
        raise Conflict("Администратор с таким Telegram ID уже есть", code="admin_exists")
    admin = AdminUser(**body.model_dump(), is_active=True)
    session.add(admin)
    await session.flush()
    await audit.record(session, ctx.admin, "admin.create", entity_type="admin", entity_id=admin.id, after=admin_user(admin), meta=ctx.meta)
    await session.commit()
    return admin_user(admin)


@router.patch("/admins/{admin_id}")
async def patch_admin(admin_id: int, body: AdminPatch, ctx: OwnerAdmin, session: SessionDep) -> dict:
    admin = await session.get(AdminUser, admin_id)
    if admin is None:
        raise NotFound("Администратор не найден", code="admin_not_found")
    if admin.telegram_id in get_settings().admin_telegram_ids and (body.is_active is False or (body.role and body.role != AdminRole.owner)):
        raise Conflict("Владелец из ADMIN_TELEGRAM_IDS управляется конфигурацией сервера", code="bootstrap_admin")
    if admin.id == ctx.admin.id and body.is_active is False:
        raise Conflict("Нельзя отключить самого себя", code="self_disable")
    before = admin_user(admin)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(admin, key, value)
    await audit.record(
        session, ctx.admin, "admin.update", entity_type="admin", entity_id=admin.id, before=before, after=admin_user(admin), meta=ctx.meta
    )
    await session.commit()
    return admin_user(admin)
