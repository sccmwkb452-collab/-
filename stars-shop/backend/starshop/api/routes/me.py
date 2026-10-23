from __future__ import annotations

from fastapi import APIRouter

from ...services.users import referral_link, user_stats
from ...shared.money import money
from ..deps import RuntimeDep, SessionDep, UserDep
from ..serializers import order_summary

router = APIRouter()


@router.get("/me")
async def me(user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    stats = await user_stats(session, user)
    return {
        "user": {
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "photo_url": user.photo_url,
            "is_premium": user.is_premium,
            "first_seen_at": user.first_seen_at.isoformat(),
            "is_blocked": user.is_blocked,
        },
        "stats": {
            "orders_count": stats.orders_count,
            "completed_count": stats.completed_count,
            "total_spent": str(money(stats.total_spent)),
            "last_order": order_summary(stats.last_order) if stats.last_order else None,
        },
        "bonus": {
            "balance": str(money(user.bonus_balance)),
            "referral_enabled": runtime.referral.enabled,
            "referral_code": user.referral_code if runtime.referral.enabled else None,
            "referral_link": referral_link(user) if runtime.referral.enabled else None,
            "invited": stats.invited_count,
            "rewarded": stats.rewarded_count,
            "reward_kind": runtime.referral.reward_kind,
            "reward_value": str(runtime.referral.reward_value),
        },
    }
