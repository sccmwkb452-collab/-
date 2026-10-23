"""Referral programme.

Rules that keep it honest:
* a referral is attached only when the invited user is seen for the first
  time (new row) — existing users cannot be "re-invited";
* no self-referrals and no mutual pairs (A invites B, B invites A);
* blocked referrers do not get new referrals;
* the reward is credited only after the invited user's order is *completed*
  (payment confirmed by the provider and Stars delivered), only for
  production orders and only once per referral (ledger dedup key);
* a gift order where the recipient is the referrer is rejected as a
  self-referral pattern;
* a refund of the qualifying order reverses the reward.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ReferralStatus, ShopMode
from ..database.models import Order, Referral, User
from ..shared.money import money, percent_of
from ..shared.timeutil import utcnow
from . import bonuses
from .app_settings import RuntimeSettings

REF_PREFIX = "ref_"


def parse_ref_code(start_param: str | None) -> str | None:
    if not start_param or not start_param.startswith(REF_PREFIX):
        return None
    code = start_param[len(REF_PREFIX) :].upper()
    return code if 4 <= len(code) <= 16 and code.isalnum() else None


async def attach(session: AsyncSession, new_user: User, start_param: str | None, runtime: RuntimeSettings) -> Referral | None:
    if not runtime.referral.enabled:
        return None
    code = parse_ref_code(start_param)
    if code is None or new_user.referred_by_id is not None:
        return None
    referrer = (await session.execute(select(User).where(User.referral_code == code))).scalar_one_or_none()
    if referrer is None or referrer.id == new_user.id or referrer.is_blocked:
        return None
    if referrer.referred_by_id == new_user.id:
        return None
    new_user.referred_by_id = referrer.id
    referral = Referral(referrer_id=referrer.id, referred_id=new_user.id, status=ReferralStatus.pending)
    session.add(referral)
    return referral


def _reward_amount(order: Order, runtime: RuntimeSettings) -> Decimal:
    cfg = runtime.referral
    if cfg.reward_kind == "percent":
        return percent_of(order.subtotal - order.discount_amount, cfg.reward_value)
    return money(cfg.reward_value)


async def on_order_completed(session: AsyncSession, order: Order, runtime: RuntimeSettings) -> None:
    referral = (
        await session.execute(
            select(Referral).where(Referral.referred_id == order.user_id, Referral.status == ReferralStatus.pending).with_for_update()
        )
    ).scalar_one_or_none()
    if referral is None or not runtime.referral.enabled or order.mode != ShopMode.production:
        return
    if order.total < runtime.referral.min_order_amount:
        return  # keep pending: a later, larger order may qualify
    referrer = await session.get(User, referral.referrer_id)
    if referrer is None or referrer.is_blocked:
        referral.status = ReferralStatus.rejected
        referral.reject_reason = "referrer_unavailable"
        return
    if (
        order.recipient_type == "username"
        and referrer.username
        and order.recipient_username
        and (order.recipient_username.lower() == referrer.username.lower())
    ):
        referral.status = ReferralStatus.rejected
        referral.reject_reason = "gift_to_referrer"
        referral.qualifying_order_id = order.id
        return
    limit = runtime.referral.max_rewards_per_referrer
    if limit is not None:
        rewarded = await session.scalar(
            select(func.count())
            .select_from(Referral)
            .where(Referral.referrer_id == referrer.id, Referral.status == ReferralStatus.rewarded)
        )
        if (rewarded or 0) >= limit:
            referral.status = ReferralStatus.rejected
            referral.reject_reason = "referrer_limit_reached"
            return
    amount = _reward_amount(order, runtime)
    if amount <= 0:
        return
    applied = await bonuses.credit(
        session,
        referrer.id,
        amount,
        kind="referral_reward",
        dedup_key=f"ref:{referral.id}",
        referral_id=referral.id,
        order_id=order.id,
        comment=f"Бонус за приглашённого пользователя, заказ #{order.number}",
    )
    referral.status = ReferralStatus.rewarded
    referral.reward_amount = applied or amount
    referral.qualifying_order_id = order.id
    referral.rewarded_at = utcnow()


async def on_order_refunded(session: AsyncSession, order: Order) -> None:
    referral = (
        await session.execute(
            select(Referral).where(Referral.qualifying_order_id == order.id, Referral.status == ReferralStatus.rewarded).with_for_update()
        )
    ).scalar_one_or_none()
    if referral is None or not referral.reward_amount:
        return
    await bonuses.debit(
        session,
        referral.referrer_id,
        referral.reward_amount,
        kind="referral_reversal",
        dedup_key=f"ref_reversal:{referral.id}",
        referral_id=referral.id,
        order_id=order.id,
        comment=f"Возврат заказа #{order.number}",
        allow_partial=True,
    )
    referral.status = ReferralStatus.reversed
