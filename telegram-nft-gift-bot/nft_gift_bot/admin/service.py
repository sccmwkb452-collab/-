"""Admin operations. Every state-changing method writes an AdminAction audit row."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.config.settings import Settings
from nft_gift_bot.models import ConnectedAccount, GiftTransfer, Payment, Subscription, SupportTicket, TicketStatus, User
from nft_gift_bot.repositories import (
    AdminActionRepository,
    ConnectedAccountRepository,
    GiftTransferRepository,
    PaymentRepository,
    SubscriptionRepository,
    SupportTicketRepository,
    UserRepository,
)
from nft_gift_bot.services.settings_service import SettingsService
from nft_gift_bot.services.subscription_service import SubscriptionService


@dataclass
class Stats:
    users: int
    active_subscriptions: int
    active_connections: int
    revenue_nano: int
    payments_by_status: dict[str, int]
    open_tickets: int


@dataclass
class UserCard:
    user: User
    subscription: Subscription | None
    account: ConnectedAccount | None
    payments: list[Payment]


class AdminService:
    def __init__(self, session: AsyncSession, settings: Settings, admin_telegram_id: int) -> None:
        self._session = session
        self._admin_id = admin_telegram_id
        self._audit = AdminActionRepository(session)
        self._users = UserRepository(session)
        self._payments = PaymentRepository(session)
        self._subs = SubscriptionRepository(session)
        self._accounts = ConnectedAccountRepository(session)
        self._transfers = GiftTransferRepository(session)
        self._tickets = SupportTicketRepository(session)
        self.settings = SettingsService(session, settings)

    def audit(self, action: str, target: str | None = None, details: dict[str, Any] | None = None) -> None:
        self._audit.add(self._admin_id, action, target, details)

    async def stats(self, now: datetime) -> Stats:
        return Stats(
            users=await self._users.count(),
            active_subscriptions=await SubscriptionService(self._session).count_active(now),
            active_connections=await self._accounts.count_active(),
            revenue_nano=await self._payments.revenue_nano(),
            payments_by_status=await self._payments.count_by_status(),
            open_tickets=len(await self._tickets.list_open(limit=1000)),
        )

    async def user_card(self, telegram_id: int) -> UserCard | None:
        self.audit("view_user", str(telegram_id))
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        return UserCard(
            user=user,
            subscription=await self._subs.get_by_user(user.id),
            account=await self._accounts.get_latest_for_user(user.id),
            payments=await self._payments.list_for_user(user.id, 5),
        )

    async def recent_users(self, limit: int = 15) -> list[User]:
        return await self._users.list_recent(limit)

    async def recent_payments(self, limit: int = 15, status: str | None = None) -> list[Payment]:
        return await self._payments.list_recent(limit, status)

    async def recent_transfers(self, limit: int = 15) -> list[GiftTransfer]:
        return await self._transfers.list_recent(limit)

    async def open_tickets(self, limit: int = 15) -> list[SupportTicket]:
        return await self._tickets.list_open(limit)

    async def reply_ticket(self, ticket_id: int, text: str, now: datetime) -> tuple[SupportTicket, User] | None:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None or ticket.status != TicketStatus.OPEN:
            return None
        user = await self._users.get(ticket.user_id)
        if user is None:
            return None
        ticket.admin_reply = text[:2000]
        ticket.answered_by = self._admin_id
        ticket.answered_at = now
        ticket.status = TicketStatus.ANSWERED
        self.audit("reply_ticket", str(ticket_id))
        return ticket, user

    async def set_blocked(self, telegram_id: int, blocked: bool) -> User | None:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        user.is_blocked = blocked
        self.audit("block_user" if blocked else "unblock_user", str(telegram_id))
        return user

    async def grant_subscription(self, telegram_id: int, days: int, now: datetime) -> Subscription | None:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        sub = await SubscriptionService(self._session).extend(user.id, days, now)
        self.audit("grant_subscription", str(telegram_id), {"days": days})
        return sub

    async def set_price(self, value: str) -> str:
        price = await self.settings.set_subscription_price(value, self._admin_id)
        self.audit("set_subscription_price", None, {"ton": str(price)})
        return str(price)

    async def set_days(self, value: str) -> int:
        days = await self.settings.set_subscription_days(value, self._admin_id)
        self.audit("set_subscription_days", None, {"days": days})
        return days

    async def set_emoji(self, key: str, custom_id: str) -> None:
        await self.settings.set_emoji(key, custom_id, self._admin_id)
        self.audit("set_emoji", key, {"custom_emoji_id": custom_id})

    async def recent_audit(self, limit: int = 15):  # noqa: ANN201
        return await self._audit.list_recent(limit)
