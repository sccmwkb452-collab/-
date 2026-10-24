from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ....database.enums import PromoKind, PromoUsageStatus, ReferralStatus
from ....database.models import BonusTransaction, PromoCode, PromoCodeUsage, Referral, User
from ....services import audit
from ....shared.errors import Conflict, NotFound, ValidationFailed
from ...deps import ManagerAdmin, SessionDep, SupportAdmin
from ...schemas import PromoIn, PromoPatch
from ...serializers import promo_admin

router = APIRouter()


async def _usage_counts(session) -> dict[int, int]:
    rows = await session.execute(
        select(PromoCodeUsage.promo_code_id, func.count())
        .where(PromoCodeUsage.status.in_((PromoUsageStatus.reserved, PromoUsageStatus.applied)))
        .group_by(PromoCodeUsage.promo_code_id)
    )
    return {pid: n for pid, n in rows.all()}


def _check(p: PromoCode) -> None:
    if p.kind == PromoKind.percent and p.value > 100:
        raise ValidationFailed("Процент скидки не может быть больше 100", code="promo_invalid")
    if p.starts_at and p.expires_at and p.expires_at <= p.starts_at:
        raise ValidationFailed("Дата окончания раньше даты начала", code="promo_invalid")


@router.get("/promo-codes")
async def list_promos(ctx: SupportAdmin, session: SessionDep) -> dict:
    counts = await _usage_counts(session)
    rows = (await session.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))).scalars()
    return {"items": [promo_admin(p, counts.get(p.id, 0)) for p in rows]}


@router.post("/promo-codes", status_code=201)
async def create_promo(body: PromoIn, ctx: ManagerAdmin, session: SessionDep) -> dict:
    promo = PromoCode(**body.model_dump())
    _check(promo)
    session.add(promo)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise Conflict("Такой промокод уже существует", code="promo_exists") from exc
    await audit.record(session, ctx.admin, "promo.create", entity_type="promo", entity_id=promo.id, after=promo_admin(promo), meta=ctx.meta)
    await session.commit()
    return promo_admin(promo)


@router.patch("/promo-codes/{promo_id}")
async def patch_promo(promo_id: int, body: PromoPatch, ctx: ManagerAdmin, session: SessionDep) -> dict:
    promo = await session.get(PromoCode, promo_id)
    if promo is None:
        raise NotFound("Промокод не найден", code="promo_not_found")
    before = promo_admin(promo)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(promo, key, value)
    _check(promo)
    await session.flush()
    await session.refresh(promo)
    await audit.record(
        session, ctx.admin, "promo.update", entity_type="promo", entity_id=promo.id, before=before, after=promo_admin(promo), meta=ctx.meta
    )
    await session.commit()
    counts = await _usage_counts(session)
    return promo_admin(promo, counts.get(promo.id, 0))


@router.delete("/promo-codes/{promo_id}")
async def disable_promo(promo_id: int, ctx: ManagerAdmin, session: SessionDep) -> dict:
    """Promo codes are deactivated, not deleted: usage history stays intact."""
    promo = await session.get(PromoCode, promo_id)
    if promo is None:
        raise NotFound("Промокод не найден", code="promo_not_found")
    promo.is_active = False
    await audit.record(session, ctx.admin, "promo.disable", entity_type="promo", entity_id=promo.id, meta=ctx.meta)
    await session.commit()
    return {"ok": True}


@router.get("/promo-codes/{promo_id}/usages")
async def promo_usages(promo_id: int, ctx: SupportAdmin, session: SessionDep) -> dict:
    rows = (
        await session.execute(
            select(PromoCodeUsage, User)
            .join(User, User.id == PromoCodeUsage.user_id)
            .where(PromoCodeUsage.promo_code_id == promo_id)
            .order_by(PromoCodeUsage.id.desc())
            .limit(500)
        )
    ).all()
    total_discount = sum((u.discount_amount for u, _ in rows if u.status == PromoUsageStatus.applied), start=0)
    return {
        "items": [
            {
                "id": u.id,
                "status": u.status,
                "discount": str(u.discount_amount),
                "order_id": str(u.order_id),
                "user": {"id": usr.id, "telegram_id": usr.telegram_id, "username": usr.username},
                "at": u.created_at.isoformat(),
            }
            for u, usr in rows
        ],
        "applied_discount_total": str(total_discount),
    }


@router.get("/referrals")
async def referrals(ctx: SupportAdmin, session: SessionDep, status: str | None = None, limit: int = 100) -> dict:
    stmt = select(Referral).order_by(Referral.id.desc()).limit(min(limit, 500))
    if status in ReferralStatus.__members__:
        stmt = stmt.where(Referral.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    summary = dict((await session.execute(select(Referral.status, func.count()).group_by(Referral.status))).all())
    rewards = await session.scalar(
        select(func.coalesce(func.sum(Referral.reward_amount), 0)).where(Referral.status == ReferralStatus.rewarded)
    )
    return {
        "summary": {"by_status": {str(k): v for k, v in summary.items()}, "rewards_total": str(rewards)},
        "items": [
            {
                "id": r.id,
                "referrer_id": r.referrer_id,
                "referred_id": r.referred_id,
                "status": r.status,
                "reject_reason": r.reject_reason,
                "reward_amount": str(r.reward_amount) if r.reward_amount else None,
                "qualifying_order_id": str(r.qualifying_order_id) if r.qualifying_order_id else None,
                "created_at": r.created_at.isoformat(),
                "rewarded_at": r.rewarded_at.isoformat() if r.rewarded_at else None,
            }
            for r in rows
        ],
    }


@router.get("/bonus-transactions")
async def bonus_transactions(
    ctx: SupportAdmin,
    session: SessionDep,
    kind: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """The bonus ledger of every user: referral rewards, reversals, spending."""
    stmt = select(BonusTransaction, User).join(User, User.id == BonusTransaction.user_id)
    count = select(func.count()).select_from(BonusTransaction)
    if kind:
        stmt = stmt.where(BonusTransaction.kind == kind)
        count = count.where(BonusTransaction.kind == kind)
    rows = (await session.execute(stmt.order_by(BonusTransaction.id.desc()).limit(limit).offset(offset))).all()
    return {
        "items": [
            {
                "id": t.id,
                "user": {"id": u.id, "telegram_id": u.telegram_id, "username": u.username, "display_name": u.display_name},
                "kind": t.kind,
                "amount": str(t.amount),
                "comment": t.comment,
                "order_id": str(t.order_id) if t.order_id else None,
                "created_at": t.created_at.isoformat(),
            }
            for t, u in rows
        ],
        "total": await session.scalar(count) or 0,
    }
