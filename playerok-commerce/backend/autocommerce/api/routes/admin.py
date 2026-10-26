"""Dashboard, journals, integration errors, security, settings and users."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from ...config import get_settings
from ...database.enums import JobStatus, NotificationStatus, OrderStatus, RoleCode, SupplierOrderStatus, SupplierStatus, SyncStatus
from ...database.models import AuditLog, AutomationJob, AutomationLog, Notification, Order, Role, Supplier, SupplierOrder, SyncRun, User
from ...services import analytics, app_settings, auth, autosettings, health, research
from ...services.audit import audit
from ...shared.errors import Conflict, DomainError, NotFound
from .. import serializers as ser
from ..deps import Context, need
from .messages import integration

router = APIRouter(tags=["admin"])


@router.get("/dashboard")
async def dashboard(ctx: Context = Depends(need("view"))) -> dict:
    s = ctx.session
    today = analytics.period("today")
    week = analytics.period("7d")
    attention = (await s.execute(select(Order).where(Order.needs_attention.is_(True)).order_by(Order.id.desc()).limit(8))).scalars().all()
    recent = (await s.execute(select(Order).order_by(Order.id.desc()).limit(8))).scalars().all()
    by_status = dict(
        (
            await s.execute(
                select(Order.status, func.count())
                .where(Order.status.not_in([OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REFUND]))
                .group_by(Order.status)
            )
        ).all()
    )
    supplier_rows = (await s.execute(select(Supplier).order_by(Supplier.id))).scalars().all()
    notes = (await s.execute(select(Notification).order_by(Notification.id.desc()).limit(8))).scalars().all()
    top, _ = await research.ranking(s, limit=5)
    return {
        "mode": "live" if await app_settings.is_live(s) else "test",
        "live_allowed": get_settings().allow_live_operations,
        "kill_switch": await app_settings.kill_switch(s),
        "health": await health.status(s),
        "today": await analytics.metrics(s, today),
        "week": await analytics.metrics(s, week),
        "series": await analytics.timeseries(s, week),
        "attention": [ser.order(o) for o in attention],
        "recent": [ser.order(o) for o in recent],
        "open_by_status": {k.value: v for k, v in by_status.items()},
        "suppliers": [
            {
                "id": x.id,
                "name": x.name,
                "status": x.status.value,
                "status_label": ser.SUPPLIER_STATUS_LABELS[x.status],
                "last_error": x.last_error,
            }
            for x in supplier_rows
        ],
        "notifications": [ser.notification(n) for n in notes],
        "integration": integration(),
        "sync": await analytics.sync_overview(s),
        "totals": await analytics.recorded_totals(s),
        "research_top": [{"product": ser.product(p), "score": ser.d(sc.total_score), "confidence": sc.confidence.value} for p, sc in top],
        "autosettings": await autosettings.overview(s),
    }


@router.get("/audit")
async def audit_log(
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    ctx: Context = Depends(need("view")),
) -> dict:
    stmt = select(AuditLog)
    if q:
        stmt = stmt.where(or_(AuditLog.action.ilike(f"%{q}%"), AuditLog.actor_name.ilike(f"%{q}%"), AuditLog.entity_id == q))
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * per_page).limit(per_page))).scalars()
    return {"items": [ser.audit_entry(a) for a in rows], "total": total, "page": page, "per_page": per_page}


@router.get("/automation-logs")
async def automation_logs(
    feature: str | None = None,
    result: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    ctx: Context = Depends(need("view")),
) -> dict:
    stmt = select(AutomationLog)
    if feature:
        stmt = stmt.where(AutomationLog.feature == feature)
    if result:
        stmt = stmt.where(AutomationLog.result == result)
    total = (await ctx.session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.session.execute(stmt.order_by(AutomationLog.id.desc()).offset((page - 1) * per_page).limit(per_page))).scalars()
    return {"items": [ser.automation_entry(a) for a in rows], "total": total, "page": page, "per_page": per_page}


@router.get("/errors")
async def integration_errors(ctx: Context = Depends(need("view"))) -> dict:
    s = ctx.session
    runs = (
        await s.execute(
            select(SyncRun).where(SyncRun.status.in_([SyncStatus.FAILED, SyncStatus.PARTIAL])).order_by(SyncRun.id.desc()).limit(50)
        )
    ).scalars()
    sup = (await s.execute(select(Supplier).where(Supplier.status == SupplierStatus.ERROR))).scalars()
    so = (
        await s.execute(
            select(SupplierOrder)
            .where(SupplierOrder.status.in_([SupplierOrderStatus.FAILED, SupplierOrderStatus.UNKNOWN]))
            .order_by(SupplierOrder.id.desc())
            .limit(50)
        )
    ).scalars()
    jobs = (
        await s.execute(select(AutomationJob).where(AutomationJob.status == JobStatus.FAILED).order_by(AutomationJob.id.desc()).limit(50))
    ).scalars()
    notes = (
        await s.execute(
            select(Notification).where(Notification.status == NotificationStatus.FAILED).order_by(Notification.id.desc()).limit(50)
        )
    ).scalars()
    logs = (
        await s.execute(select(AutomationLog).where(AutomationLog.result == "error").order_by(AutomationLog.id.desc()).limit(50))
    ).scalars()
    return {
        "sync_runs": [ser.sync_run(r) for r in runs],
        "suppliers": [ser.supplier(x) for x in sup],
        "supplier_orders": [ser.supplier_order(x) for x in so],
        "jobs": [
            {
                "id": j.id,
                "kind": j.kind,
                "attempts": j.attempts,
                "last_error": j.last_error,
                "payload": j.payload,
                "finished_at": ser.dt(j.finished_at),
            }
            for j in jobs
        ],
        "notifications": [ser.notification(n) for n in notes],
        "automation": [ser.automation_entry(a) for a in logs],
        "integration": integration(),
    }


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: int, ctx: Context = Depends(need("settings.manage"))) -> dict:
    job = await ctx.session.get(AutomationJob, job_id)
    if job is None:
        raise NotFound("Задача не найдена")
    if job.status is not JobStatus.FAILED:
        raise Conflict("Повторить можно только задачу с ошибкой")
    from ...shared.timeutil import utcnow

    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.run_after = utcnow()
    await audit(ctx.session, ctx.actor, "job.retry", entity_type="job", entity_id=job.id)
    return {"ok": True}


@router.get("/notifications")
async def notifications(page: int = Query(1, ge=1), ctx: Context = Depends(need("view"))) -> dict:
    rows = (await ctx.session.execute(select(Notification).order_by(Notification.id.desc()).offset((page - 1) * 50).limit(50))).scalars()
    return {"items": [ser.notification(n) for n in rows], "kinds": app_settings.NOTIFICATION_KINDS}


@router.get("/health/details")
async def health_details(ctx: Context = Depends(need("view"))) -> dict:
    return await health.status(ctx.session)


@router.get("/security")
async def security(ctx: Context = Depends(need("view"))) -> dict:
    s = ctx.session
    failed = (
        await s.execute(
            select(AuditLog).where(AuditLog.action.in_(["auth.login_failed", "auth.totp_failed"])).order_by(AuditLog.id.desc()).limit(20)
        )
    ).scalars()
    admin_actions = (
        await s.execute(select(AuditLog).where(AuditLog.actor_type.in_(["web", "telegram", "cli"])).order_by(AuditLog.id.desc()).limit(20))
    ).scalars()
    return {
        "kill_switch": await app_settings.kill_switch(s),
        "mode": "live" if await app_settings.is_live(s) else "test",
        "live_allowed": get_settings().allow_live_operations,
        "failed_logins": [ser.audit_entry(a) for a in failed],
        "admin_actions": [ser.audit_entry(a) for a in admin_actions],
        "session_hours": get_settings().session_hours,
        "session_idle_minutes": get_settings().session_idle_minutes,
        "user": ser.user(ctx.user),
    }


class KillIn(BaseModel):
    active: bool
    reason: str = Field(default="", max_length=300)


@router.post("/security/kill-switch")
async def kill_switch(body: KillIn, ctx: Context = Depends(need("security.manage"))) -> dict:
    return await app_settings.set_kill_switch(ctx.session, body.active, ctx.actor, body.reason)


class ModeIn(BaseModel):
    mode: str


@router.post("/security/mode")
async def mode(body: ModeIn, ctx: Context = Depends(need("settings.manage"))) -> dict:
    if body.mode == "live" and "*" not in ctx.actor.permissions:
        raise DomainError("Боевой режим включает только владелец")
    await app_settings.set_setting(ctx.session, "operations.mode", body.mode, ctx.actor)
    return {"mode": "live" if await app_settings.is_live(ctx.session) else "test"}


EDITABLE_SETTINGS = ("notifications", "reports.daily", "reports.weekly", "shop.profile", "orders.auto_pipeline", "research.weights")


@router.get("/settings")
async def get_settings_view(ctx: Context = Depends(need("view"))) -> dict:
    values = await app_settings.get_many(ctx.session, list(EDITABLE_SETTINGS))
    return {"values": values, "notification_kinds": app_settings.NOTIFICATION_KINDS, "timezone": get_settings().display_timezone}


class SettingIn(BaseModel):
    value: Any


@router.put("/settings/{key}")
async def put_setting(key: str, body: SettingIn, ctx: Context = Depends(need("settings.manage"))) -> dict:
    if key not in EDITABLE_SETTINGS:
        raise NotFound("Настройка не найдена")
    return {"key": key, "value": await app_settings.set_setting(ctx.session, key, body.value, ctx.actor)}


@router.post("/settings/{key}/reset")
async def reset_setting(key: str, ctx: Context = Depends(need("settings.manage"))) -> dict:
    if key not in EDITABLE_SETTINGS:
        raise NotFound("Настройка не найдена")
    return {"key": key, "value": await app_settings.reset_setting(ctx.session, key, ctx.actor)}


@router.get("/users")
async def users(ctx: Context = Depends(need("users.manage"))) -> dict:
    rows = (await ctx.session.execute(select(User).order_by(User.id))).scalars()
    roles = (await ctx.session.execute(select(Role).order_by(Role.id))).scalars()
    return {
        "items": [ser.user(u) for u in rows],
        "roles": [{"code": r.code.value, "name": r.name, "permissions": r.permissions} for r in roles],
        "permissions": auth.ALL_PERMISSIONS,
    }


class UserIn(BaseModel):
    email: str = Field(max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=200)
    role: RoleCode = RoleCode.OPERATOR


@router.post("/users")
async def create_user(body: UserIn, ctx: Context = Depends(need("users.manage"))) -> dict:
    if body.role is RoleCode.OWNER:
        raise DomainError("Нового владельца создаёт только CLI (create-admin)")
    user = await auth.create_user(
        ctx.session, email=body.email, password=body.password, display_name=body.display_name, role=body.role, actor=ctx.actor
    )
    return ser.user(user)


class UserPatch(BaseModel):
    role: RoleCode | None = None
    is_active: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    unlink_telegram: bool = False


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: UserPatch, ctx: Context = Depends(need("users.manage"))) -> dict:
    user = await ctx.session.get(User, user_id)
    if user is None:
        raise NotFound("Пользователь не найден")
    if user.id == ctx.user.id and (body.is_active is False or (body.role and body.role is not RoleCode.OWNER)):
        raise DomainError("Нельзя отключить себя или понизить свою роль")
    if body.role is RoleCode.OWNER:
        raise DomainError("Роль владельца назначается только через CLI")
    if body.role is not None:
        roles = await auth.ensure_roles(ctx.session)
        user.role_id = roles[body.role].id
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            await auth.revoke_all_sessions(ctx.session, user.id)
    if body.display_name:
        user.display_name = body.display_name
    if body.unlink_telegram:
        user.telegram_id = None
    await audit(
        ctx.session,
        ctx.actor,
        "user.update",
        entity_type="user",
        entity_id=user.id,
        details=body.model_dump(exclude_none=True, mode="json"),
    )
    await ctx.session.flush()
    await ctx.session.refresh(user, ["role"])
    return ser.user(user)


class ResetIn(BaseModel):
    password: str = Field(min_length=10, max_length=200)


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, body: ResetIn, ctx: Context = Depends(need("users.manage"))) -> dict:
    user = await ctx.session.get(User, user_id)
    if user is None:
        raise NotFound("Пользователь не найден")
    await auth.set_password(ctx.session, user, body.password, ctx.actor)
    return {"ok": True}
