from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import nft_gift_bot.models  # noqa: F401
from nft_gift_bot.database.base import Base
from nft_gift_bot.gifts.api import GiftApiError, OwnedGiftInfo
from nft_gift_bot.gifts.recipient import RecipientRef, ResolvedRecipient
from nft_gift_bot.models import User
from nft_gift_bot.payments.verifier import IncomingTransfer
from nft_gift_bot.services.crypto import SecretBox, generate_key
from nft_gift_bot.services.subscription_service import SubscriptionService
from nft_gift_bot.telegram_accounts.service import AccountConnectionService, BusinessConnectionEvent

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    # Set TEST_DATABASE_URL=postgresql+asyncpg://... to run the suite against PostgreSQL.
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_async_engine(url)
    else:
        engine = create_async_engine(
            "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def box() -> SecretBox:
    return SecretBox(generate_key())


async def make_user(session: AsyncSession, telegram_id: int = 1001, username: str = "owner") -> User:
    user = User(telegram_id=telegram_id, username=username)
    session.add(user)
    await session.flush()
    return user


async def subscribe(session: AsyncSession, user: User, days: int = 30, now: datetime = NOW) -> None:
    await SubscriptionService(session).extend(user.id, days, now)
    await session.flush()


async def connect(
    session: AsyncSession, box: SecretBox, user: User, connection_id: str = "bc-secret-1", **rights: bool
) -> None:
    event = BusinessConnectionEvent(
        connection_id=connection_id,
        owner_telegram_id=user.telegram_id,
        is_enabled=True,
        can_view_gifts=rights.get("view", True),
        can_transfer_gifts=rights.get("transfer", True),
        can_transfer_stars=rights.get("stars", True),
    )
    await AccountConnectionService(session, box).handle_event(event, NOW)
    await session.flush()


@dataclass
class FakeChain:
    transfers: list[IncomingTransfer] = field(default_factory=list)
    calls: int = 0

    async def get_incoming_transfers(self, address: str, limit: int = 100) -> list[IncomingTransfer]:
        self.calls += 1
        return list(self.transfers)


@dataclass
class FakeGiftApi:
    gifts: list[OwnedGiftInfo] = field(default_factory=list)
    known_users: dict[str, int] = field(default_factory=lambda: {"alice": 2002})
    transfer_error: GiftApiError | None = None
    transfers: list[tuple[str, str, int, int | None]] = field(default_factory=list)

    async def list_owned_gifts(self, connection_id: str) -> list[OwnedGiftInfo]:
        return list(self.gifts)

    async def resolve_recipient(self, ref: RecipientRef) -> ResolvedRecipient:
        if ref.user_id is not None:
            return ResolvedRecipient(ref.user_id, ref.label, verified=False)
        if ref.username not in self.known_users:
            raise GiftApiError("recipient_not_found", "not found")
        return ResolvedRecipient(self.known_users[ref.username], f"@{ref.username}", verified=True)

    async def transfer(self, connection_id: str, owned_gift_id: str, new_owner_chat_id: int, star_count: int | None) -> None:
        if self.transfer_error:
            raise self.transfer_error
        self.transfers.append((connection_id, owned_gift_id, new_owner_chat_id, star_count))


def unique_gift(owned_id: str = "og-1", title: str = "Plush Pepe #12", fee: int | None = 25, **kw) -> OwnedGiftInfo:
    return OwnedGiftInfo(
        owned_gift_id=owned_id,
        title=title,
        is_unique=True,
        can_be_transferred=kw.get("can_be_transferred", True),
        transfer_star_count=fee,
        next_transfer_date=kw.get("next_transfer_date"),
        unique_name=kw.get("unique_name", title.replace(" ", "").replace("#", "-")),
    )


def later(minutes: int) -> datetime:
    return NOW + timedelta(minutes=minutes)
