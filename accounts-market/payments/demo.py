"""DEMO provider for development and testing. Refuses to run in production.

It imitates a payment provider's server: invoices live in its own memory and
change state only through `simulate_payment`, which the bot exposes as a
clearly labelled DEMO button. The shop then checks the status exactly the way
it does with a real provider.
"""

from __future__ import annotations

from payments.base import Invoice, InvoiceRequest, PaymentProvider, ProviderError, ProviderStatus


class DemoProvider(PaymentProvider):
    name = "demo"
    title = "DEMO"
    is_demo = True
    supports_refund = True

    def __init__(self) -> None:
        self._invoices: dict[str, dict] = {}

    async def create_invoice(self, request: InvoiceRequest) -> Invoice:
        external_id = f"demo-{request.uid}"
        self._invoices[external_id] = {"amount": request.amount, "state": "pending"}
        return Invoice(external_id=external_id, pay_url=None)

    async def fetch_status(self, external_id: str) -> ProviderStatus:
        invoice = self._invoices.get(external_id)
        if invoice is None:
            # Unknown after a restart: the demo server forgot it, treat as unpaid.
            return ProviderStatus("pending")
        return ProviderStatus(invoice["state"], invoice["amount"], "RUB")

    def simulate_payment(self, external_id: str, amount: int) -> None:
        invoice = self._invoices.setdefault(external_id, {"amount": amount, "state": "pending"})
        if invoice["state"] == "pending":
            invoice["state"] = "paid"

    async def refund(self, external_id: str, amount: int) -> None:
        if external_id not in self._invoices:
            raise ProviderError("DEMO: счёт не найден")
