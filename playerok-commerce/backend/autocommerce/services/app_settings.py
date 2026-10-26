"""Runtime settings stored in the ``settings`` table.

Each key has a default here, so a fresh database works and «Сбросить» restores
the documented values. Writes go through ``set_setting`` which validates the
value and writes an audit record.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.models import Setting
from ..shared.errors import Blocked, DomainError
from ..shared.timeutil import utcnow
from .audit import Actor, audit

NOTIFICATION_KINDS: dict[str, str] = {
    "order_new": "🛒 Новые заказы",
    "order_attention": "⚠️ Заказ требует внимания",
    "order_status": "🔄 Смена статуса заказа",
    "customer_message": "💬 Сообщения покупателей",
    "review": "⭐ Отзывы",
    "purchase_confirm": "✋ Подтверждение закупки",
    "manual_purchase": "🛒 Требуется ручная закупка",
    "price_alert": "💰 Цены и маржа",
    "supplier_error": "🏪 Ошибки поставщиков",
    "stock_low": "📦 Мало товара",
    "operator_hint": "💡 Подсказки оператору",
    "listing": "📝 Объявления",
    "report": "📊 Отчёты",
    "system": "🛠 Система и безопасность",
}

DEFAULTS: dict[str, Any] = {
    "operations.mode": None,  # resolved from APP_MODE at read time
    "automation.kill_switch": {"active": False, "reason": "", "at": None, "by": None},
    "notifications": {
        "kinds": {k: True for k in NOTIFICATION_KINDS},
        "quiet_hours": {"enabled": False, "start": "23:00", "end": "08:00"},
    },
    "reports.daily": {"enabled": True, "hour": 9},
    "reports.weekly": {"enabled": True, "weekday": 1, "hour": 10},
    "shop.profile": {"name": "Мой магазин на PlayerOK", "playerok_profile_url": "", "operator_contact": ""},
    "marketplace.adapter": "playerok_manual",
    "listings.bulk_confirmed": False,
    "orders.auto_pipeline": True,
    "research.weights": {
        "demand": 20,
        "margin": 20,
        "turnover": 10,
        "competition": 10,
        "supplier_stability": 10,
        "dispute_risk": 10,
        "supplier_reliability": 10,
        "freshness": 5,
        "auto_delivery": 5,
    },
}


def _default(key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(key)
    if key == "operations.mode":
        return get_settings().app_mode
    return copy.deepcopy(DEFAULTS[key])


def _merge(default: Any, stored: Any) -> Any:
    """Stored dicts are merged over defaults so new fields get their default."""
    if isinstance(default, dict) and isinstance(stored, dict):
        out = copy.deepcopy(default)
        for k, v in stored.items():
            out[k] = _merge(default.get(k), v) if k in default else v
        return out
    return stored if stored is not None else default


async def get_setting(session: AsyncSession, key: str) -> Any:
    row = await session.get(Setting, key)
    default = _default(key)
    if row is None:
        return default
    return _merge(default, row.value)


async def get_many(session: AsyncSession, keys: list[str]) -> dict[str, Any]:
    rows = {r.key: r for r in (await session.execute(select(Setting).where(Setting.key.in_(keys)))).scalars()}
    return {k: _merge(_default(k), rows[k].value) if k in rows else _default(k) for k in keys}


def _validate(key: str, value: Any) -> Any:
    if key == "operations.mode":
        if value not in ("test", "live"):
            raise DomainError("Режим должен быть test или live")
        if value == "live" and not get_settings().allow_live_operations:
            raise Blocked("Боевой режим запрещён: на сервере не задано ALLOW_LIVE_OPERATIONS=true")
    elif key == "reports.daily":
        hour = int(value.get("hour", 9))
        if not 0 <= hour <= 23:
            raise DomainError("Час отчёта — от 0 до 23")
        value = {"enabled": bool(value.get("enabled")), "hour": hour}
    elif key == "notifications":
        kinds = {k: bool(v) for k, v in (value.get("kinds") or {}).items() if k in NOTIFICATION_KINDS}
        qh = value.get("quiet_hours") or {}
        for field in ("start", "end"):
            text = str(qh.get(field, "00:00"))
            hh, _, mm = text.partition(":")
            if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise DomainError("Время тихих часов в формате ЧЧ:ММ")
        value = {"kinds": kinds, "quiet_hours": {"enabled": bool(qh.get("enabled")), "start": qh["start"], "end": qh["end"]}}
    elif key == "research.weights":
        value = {k: max(0, min(100, int(v))) for k, v in value.items() if k in DEFAULTS["research.weights"]}
    return value


async def set_setting(session: AsyncSession, key: str, value: Any, actor: Actor) -> Any:
    _default(key)  # unknown key -> KeyError
    value = _validate(key, value)
    before = await get_setting(session, key)
    stmt = insert(Setting).values(key=key, value=value, updated_by=actor.label, updated_at=utcnow())
    stmt = stmt.on_conflict_do_update(
        index_elements=[Setting.key], set_={"value": value, "updated_by": actor.label, "updated_at": utcnow()}
    )
    await session.execute(stmt)
    await audit(session, actor, "settings.update", entity_type="setting", entity_id=key, details={"before": before, "after": value})
    return value


async def reset_setting(session: AsyncSession, key: str, actor: Actor) -> Any:
    row = await session.get(Setting, key)
    if row is not None:
        await session.delete(row)
    await audit(session, actor, "settings.reset", entity_type="setting", entity_id=key)
    return _default(key)


# --- operations mode and kill switch ---------------------------------------


async def is_live(session: AsyncSession) -> bool:
    """Live operations need both the env permission and the panel switch."""
    if not get_settings().allow_live_operations:
        return False
    return await get_setting(session, "operations.mode") == "live"


async def kill_switch(session: AsyncSession) -> dict[str, Any]:
    return await get_setting(session, "automation.kill_switch")


async def automation_stopped(session: AsyncSession) -> bool:
    return bool((await kill_switch(session)).get("active"))


async def set_kill_switch(session: AsyncSession, active: bool, actor: Actor, reason: str = "") -> dict[str, Any]:
    value = {"active": active, "reason": reason[:300], "at": utcnow().isoformat(), "by": actor.label}
    stmt = insert(Setting).values(key="automation.kill_switch", value=value, updated_by=actor.label)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Setting.key], set_={"value": value, "updated_by": actor.label, "updated_at": utcnow()}
    )
    await session.execute(stmt)
    await audit(session, actor, "automation.kill_switch", details={"active": active, "reason": reason})
    return value
