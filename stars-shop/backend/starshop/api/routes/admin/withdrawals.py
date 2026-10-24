"""Payouts of referral bonuses as Stars: review, approve, reject, return."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from ....database.enums import WithdrawalStatus
from ....database.models import Order, User, Withdrawal
from ....services import audit, withdrawals
from ....shared.errors import NotFound
from ...deps import ManagerAdmin, RuntimeDep, SessionDep, SupportAdmin
from ...schemas import WithdrawalRejectIn

router = APIRouter(prefix="/withdrawals")


def _row(w: Withdrawal, u: User, order: Order | None) -> dict:
    return withdrawals.serialize(w, order) | {
        "user": {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "display_name": u.display_name,
            "bonus_balance": str(u.bonus_balance),
        },
        "rate": str(w.rate),
    }


@router.get("")
async def list_withdrawals(
    ctx: SupportAdmin,
    session: SessionDep,
    status: Annotated[WithdrawalStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(Withdrawal, User, Order).join(User, User.id == Withdrawal.user_id).outerjoin(Order, Order.id == Withdrawal.order_id)
    count = select(func.count()).select_from(Withdrawal)
    if status is not None:
        stmt = stmt.where(Withdrawal.status == status)
        count = count.where(Withdrawal.status == status)
    rows = (await session.execute(stmt.order_by(Withdrawal.id.desc()).limit(limit).offset(offset))).all()
    pending = await session.scalar(select(func.count()).select_from(Withdrawal).where(Withdrawal.status == WithdrawalStatus.pending))
    return {"items": [_row(w, u, o) for w, u, o in rows], "total": await session.scalar(count) or 0, "pending": pending or 0}


async def _get(session, withdrawal_id: int) -> Withdrawal:
    w = await session.get(Withdrawal, withdrawal_id)
    if w is None:
        raise NotFound("Заявка не найдена", code="withdrawal_not_found")
    return w


async def _done(session, ctx, w: Withdrawal, action: str, extra: dict | None = None) -> dict:
    await audit.record(
        session, ctx.admin, action, entity_type="withdrawal", entity_id=w.id, after={"status": w.status, **(extra or {})}, meta=ctx.meta
    )
    await session.commit()
    user = await session.get(User, w.user_id)
    order = await session.get(Order, w.order_id) if w.order_id else None
    return _row(w, user, order)


@router.post("/{withdrawal_id}/approve")
async def approve(withdrawal_id: int, ctx: ManagerAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    w = await _get(session, withdrawal_id)
    order = await withdrawals.approve(session, w, runtime, admin_id=ctx.admin.id)
    return await _done(session, ctx, w, "withdrawal.approve", {"order": order.number})


@router.post("/{withdrawal_id}/reject")
async def reject(withdrawal_id: int, body: WithdrawalRejectIn, ctx: ManagerAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    w = await _get(session, withdrawal_id)
    await withdrawals.reject(session, w, runtime, admin_id=ctx.admin.id, comment=body.comment)
    return await _done(session, ctx, w, "withdrawal.reject", {"comment": body.comment})


@router.post("/{withdrawal_id}/return")
async def return_bonus(withdrawal_id: int, ctx: ManagerAdmin, session: SessionDep, runtime: RuntimeDep) -> dict:
    w = await _get(session, withdrawal_id)
    await withdrawals.return_failed(session, w, runtime, admin_id=ctx.admin.id)
    return await _done(session, ctx, w, "withdrawal.return")
