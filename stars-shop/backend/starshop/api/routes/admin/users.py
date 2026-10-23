from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from ....database.models import AdminAuditLog, AdminUser, BonusTransaction, Order, Referral, User, UserNote
from ....services import audit
from ....services.users import user_stats
from ....shared.errors import NotFound
from ....shared.money import money
from ....shared.timeutil import utcnow
from ...deps import ManagerAdmin, SessionDep, SupportAdmin
from ...schemas import BlockIn, NoteIn
from ...serializers import audit_admin, order_admin, user_admin

router = APIRouter(prefix="/users")


@router.get("")
async def list_users(
    ctx: SupportAdmin,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=64)] = None,
    blocked: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(User)
    if q:
        q = q.strip().lstrip("@")
        conds = [User.username.ilike(f"%{q}%"), User.first_name.ilike(f"%{q}%"), User.referral_code == q.upper()]
        if q.isdigit():
            conds.append(User.telegram_id == int(q))
        stmt = stmt.where(or_(*conds))
    if blocked is not None:
        stmt = stmt.where(User.is_blocked.is_(blocked))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await session.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))).scalars()
    return {"items": [user_admin(u) for u in rows], "total": total or 0}


async def _user(session, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("Пользователь не найден", code="user_not_found")
    return user


@router.get("/{user_id}")
async def get_user(user_id: int, ctx: SupportAdmin, session: SessionDep) -> dict:
    user = await _user(session, user_id)
    stats = await user_stats(session, user)
    orders = (
        (await session.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(50))).scalars().all()
    )
    notes = (
        await session.execute(
            select(UserNote, AdminUser)
            .outerjoin(AdminUser, AdminUser.id == UserNote.admin_id)
            .where(UserNote.user_id == user.id)
            .order_by(UserNote.id.desc())
        )
    ).all()
    logs = (
        await session.execute(
            select(AdminAuditLog)
            .where(AdminAuditLog.entity_type == "user", AdminAuditLog.entity_id == str(user.id))
            .order_by(AdminAuditLog.id.desc())
            .limit(50)
        )
    ).scalars()
    bonus = (
        await session.execute(
            select(BonusTransaction).where(BonusTransaction.user_id == user.id).order_by(BonusTransaction.id.desc()).limit(50)
        )
    ).scalars()
    referrals = (
        await session.execute(select(Referral).where(Referral.referrer_id == user.id).order_by(Referral.id.desc()).limit(50))
    ).scalars()
    return {
        "user": user_admin(user),
        "stats": {
            "orders_count": stats.orders_count,
            "completed_count": stats.completed_count,
            "total_spent": str(money(stats.total_spent)),
            "invited": stats.invited_count,
            "rewarded": stats.rewarded_count,
        },
        "orders": [order_admin(o, user) for o in orders],
        "notes": [
            {
                "id": n.id,
                "text": n.text,
                "admin": (a.display_name or a.username or str(a.telegram_id)) if a else None,
                "at": n.created_at.isoformat(),
            }
            for n, a in notes
        ],
        "audit": [audit_admin(log) for log in logs],
        "bonus_transactions": [
            {
                "id": b.id,
                "amount": str(b.amount),
                "kind": b.kind,
                "comment": b.comment,
                "order_id": str(b.order_id) if b.order_id else None,
                "at": b.created_at.isoformat(),
            }
            for b in bonus
        ],
        "referrals": [
            {
                "id": r.id,
                "referred_id": r.referred_id,
                "status": r.status,
                "reward_amount": str(r.reward_amount) if r.reward_amount else None,
                "reject_reason": r.reject_reason,
                "at": r.created_at.isoformat(),
            }
            for r in referrals
        ],
    }


@router.post("/{user_id}/block")
async def block(user_id: int, body: BlockIn, ctx: ManagerAdmin, session: SessionDep) -> dict:
    user = await _user(session, user_id)
    user.is_blocked = True
    user.blocked_reason = body.reason
    user.blocked_at = utcnow()
    await audit.record(session, ctx.admin, "user.block", entity_type="user", entity_id=user.id, summary=body.reason, meta=ctx.meta)
    await session.commit()
    return user_admin(user)


@router.post("/{user_id}/unblock")
async def unblock(user_id: int, ctx: ManagerAdmin, session: SessionDep) -> dict:
    user = await _user(session, user_id)
    user.is_blocked = False
    user.blocked_reason = None
    user.blocked_at = None
    await audit.record(session, ctx.admin, "user.unblock", entity_type="user", entity_id=user.id, meta=ctx.meta)
    await session.commit()
    return user_admin(user)


@router.post("/{user_id}/notes", status_code=201)
async def add_note(user_id: int, body: NoteIn, ctx: SupportAdmin, session: SessionDep) -> dict:
    user = await _user(session, user_id)
    note = UserNote(user_id=user.id, admin_id=ctx.admin.id, text=body.text)
    session.add(note)
    await audit.record(session, ctx.admin, "user.note", entity_type="user", entity_id=user.id, summary=body.text[:200], meta=ctx.meta)
    await session.commit()
    return {"id": note.id, "text": note.text, "at": note.created_at.isoformat()}
