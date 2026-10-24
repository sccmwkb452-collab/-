"""Telegram Premium as a gift from the bot (Bot API ``giftPremiumSubscription``).

Telegram takes the price from the bot's own Stars balance: 1000 Stars for
3 months, 1500 for 6 and 2500 for 12. The bot can gift only to a known
Telegram ID, so the recipient must be the buyer or another user of the shop.
Top up the bot's balance before selling (@BotFather → Bot → Balance, or buy
Stars for the bot account on Fragment)."""

from __future__ import annotations

import httpx

from ..config import Settings
from ..shared.items import PREMIUM_GIFT_STARS
from .base import DeliveryError, DeliveryOutcome, DeliveryProvider, DeliveryRequest


class TelegramPremiumDeliveryProvider(DeliveryProvider):
    name = "telegram_premium"
    title = "Telegram Premium в подарок от бота"
    idempotent = False
    supports_stars = False
    supports_premium = True
    requires_username = False
    requires_telegram_id = True

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._token = settings.bot_token.get_secret_value()
        self._base = settings.telegram_api_base.rstrip("/")
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self._token)

    async def deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        if request.is_demo:
            raise DeliveryError("DEMO-заказ нельзя выполнить подарком с баланса бота", retryable=False, definitely_not_executed=True)
        months = request.premium_months
        if months not in PREMIUM_GIFT_STARS or not request.recipient_telegram_id:
            raise DeliveryError("Нужен Premium-заказ с известным Telegram ID получателя", retryable=False, definitely_not_executed=True)
        payload = {
            "user_id": request.recipient_telegram_id,
            "month_count": months,
            "star_count": PREMIUM_GIFT_STARS[months],
            "text": f"Подарок по заказу #{request.order_number}",
        }
        try:
            async with httpx.AsyncClient(timeout=20, transport=self._transport) as client:
                response = await client.post(f"{self._base}/bot{self._token}/giftPremiumSubscription", json=payload)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # The outcome is unknown: the gift may have gone through.
            raise DeliveryError(f"Telegram недоступен: {type(exc).__name__}", retryable=True) from None
        if data.get("ok"):
            return DeliveryOutcome(status="succeeded", external_id=f"tg-premium-{request.order_number}", message="Premium подарен ботом")
        description = str(data.get("description") or "ошибка Telegram")
        if "BALANCE" in description.upper() or "STARS" in description.upper():
            return DeliveryOutcome(
                status="needs_attention",
                message=f"На балансе бота не хватает звёзд ({PREMIUM_GIFT_STARS[months]} ⭐ нужно): пополните и повторите доставку",
                details={"telegram": description[:200]},
            )
        # Telegram rejected the request: nothing was charged.
        raise DeliveryError(f"Telegram отклонил подарок: {description[:200]}", retryable=False, definitely_not_executed=True)
