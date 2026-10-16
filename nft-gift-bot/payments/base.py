"""Абстрактный интерфейс провайдера платежей."""
import abc
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class PaymentInvoice:
    provider: str
    amount: Decimal
    currency: str
    title: str
    description: str
    payload: str           # Произвольные данные для идентификации платежа
    invoice_url: str = ""  # Ссылка для оплаты (если провайдер возвращает URL)
    extra: dict = field(default_factory=dict)


@dataclass
class PaymentResult:
    success: bool
    provider_payment_id: str = ""
    provider_charge_id: str = ""
    error_message: str = ""
    extra: dict = field(default_factory=dict)


class BasePaymentProvider(abc.ABC):
    """Интерфейс, который должен реализовать каждый провайдер."""

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    @abc.abstractmethod
    async def create_invoice(
        self,
        amount: Decimal,
        currency: str,
        title: str,
        description: str,
        payload: str,
    ) -> PaymentInvoice: ...

    @abc.abstractmethod
    async def verify_payment(self, payment_id: str) -> PaymentResult: ...

    @abc.abstractmethod
    async def refund(self, payment_id: str) -> PaymentResult: ...
