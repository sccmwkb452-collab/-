from __future__ import annotations

from .base import DeliveryError, DeliveryOutcome, DeliveryProvider, DeliveryRequest, RecipientCheck


class DemoDeliveryProvider(DeliveryProvider):
    """DEMO only. Marks the order as fulfilled *without sending any Stars*.

    Recipients containing ``demo_fail`` simulate a permanent supplier error,
    ``demo_retry`` a temporary one — handy for trying the failure screens."""

    name = "demo"
    title = "DEMO-доставка (Stars не отправляются)"
    is_demo = True
    idempotent = True
    requires_username = False

    async def deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        if not request.is_demo:
            raise DeliveryError("DEMO delivery cannot fulfil production orders", retryable=False, definitely_not_executed=True)
        username = (request.recipient_username or "").lower()
        if "demo_fail" in username:
            raise DeliveryError("DEMO: поставщик отклонил заказ", retryable=False, definitely_not_executed=True)
        if "demo_retry" in username:
            raise DeliveryError("DEMO: временная ошибка поставщика", retryable=True, definitely_not_executed=True)
        return DeliveryOutcome(
            status="succeeded",
            external_id=f"demo-{request.order_number}",
            message="DEMO: реальные Stars не отправлялись",
            details={"demo": True},
        )

    async def check_recipient(self, username: str) -> RecipientCheck:
        return RecipientCheck(ok=True, display_name=f"@{username}")
