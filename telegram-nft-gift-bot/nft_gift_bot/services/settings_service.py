"""Runtime settings with admin overrides stored in the database."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.config.emoji import EMOJI_KEYS
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.payments.ton import ton_to_nano
from nft_gift_bot.repositories import BotSettingsRepository

PRICE_KEY = "subscription.price_ton"
DAYS_KEY = "subscription.days"
EMOJI_PREFIX = "emoji."

MAX_SUBSCRIPTION_DAYS = 3650


class SettingsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._repo = BotSettingsRepository(session)
        self._settings = settings

    async def subscription_price_ton(self) -> Decimal:
        raw = await self._repo.get(PRICE_KEY)
        return Decimal(raw) if raw else self._settings.subscription_price_ton

    async def subscription_price_nano(self) -> int:
        return ton_to_nano(await self.subscription_price_ton())

    async def subscription_days(self) -> int:
        raw = await self._repo.get(DAYS_KEY)
        return int(raw) if raw else self._settings.subscription_days

    async def set_subscription_price(self, value: str, admin_id: int) -> Decimal:
        ton_to_nano(value)  # validates positive amount with <= 9 decimals
        price = Decimal(value)
        await self._repo.set(PRICE_KEY, str(price), admin_id)
        return price

    async def set_subscription_days(self, value: str, admin_id: int) -> int:
        if not value.isdigit() or not 1 <= int(value) <= MAX_SUBSCRIPTION_DAYS:
            raise ValueError(f"Days must be an integer from 1 to {MAX_SUBSCRIPTION_DAYS}")
        await self._repo.set(DAYS_KEY, value, admin_id)
        return int(value)

    async def emoji_overrides(self) -> dict[str, str]:
        rows = await self._repo.list_prefix(EMOJI_PREFIX)
        return {key.removeprefix(EMOJI_PREFIX): value for key, value in rows.items()}

    async def set_emoji(self, key: str, custom_id: str, admin_id: int) -> None:
        if key not in EMOJI_KEYS:
            raise ValueError(f"Unknown emoji key. Available: {', '.join(EMOJI_KEYS)}")
        if not (custom_id.isdigit() and len(custom_id) <= 32) and custom_id != "-":
            raise ValueError("Custom emoji ID must be digits (or '-' to reset to fallback)")
        await self._repo.set(EMOJI_PREFIX + key, "" if custom_id == "-" else custom_id, admin_id)
