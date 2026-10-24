from __future__ import annotations

from .base import DeliveryOutcome, DeliveryProvider, DeliveryRequest


class ManualDeliveryProvider(DeliveryProvider):
    """Operator-fulfilled delivery.

    The task is parked as *needs_attention* and the admins get an alert. An
    operator buys the Stars for the recipient on https://fragment.com (the
    official Telegram platform for Stars, paid with TON) and confirms the
    delivery in the admin panel with the transaction reference. The order is
    completed — and the customer notified — only after that confirmation."""

    name = "manual"
    title = "Ручная доставка оператором (Fragment)"
    idempotent = False
    requires_username = True

    async def deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        return DeliveryOutcome(
            status="needs_attention",
            message=(
                f"Ожидает выполнения оператором: подарите Telegram Premium на {request.premium_months} мес. на Fragment и подтвердите доставку в админ-панели"
                if request.premium_months
                else "Ожидает выполнения оператором: купите Stars на Fragment и подтвердите доставку в админ-панели"
            ),
            details={"manual": True},
        )
