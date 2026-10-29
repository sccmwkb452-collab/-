from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Owner, TradingPolicy


async def get_or_create_owner(
    session: AsyncSession, telegram_id: int, first_name: str | None = None, username: str | None = None
) -> Owner:
    owner = await session.scalar(select(Owner).where(Owner.telegram_id == telegram_id))
    if owner is None:
        owner = Owner(telegram_id=telegram_id, first_name=first_name, username=username)
        session.add(owner)
        await session.flush()
    elif first_name or username:
        owner.first_name = first_name or owner.first_name
        owner.username = username or owner.username
    return owner


async def get_policy(session: AsyncSession, owner_id: int) -> TradingPolicy:
    policy = await session.scalar(select(TradingPolicy).where(TradingPolicy.owner_id == owner_id))
    if policy is None:
        policy = TradingPolicy(owner_id=owner_id)
        session.add(policy)
        await session.flush()
    return policy
