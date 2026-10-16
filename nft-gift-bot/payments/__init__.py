"""
Модуль обработки платежей.

Поддерживаемые провайдеры (будут реализованы):
- TelegramStarsProvider  — оплата через Telegram Stars (XTR)
- CryptoBotProvider      — оплата криптовалютой через @CryptoBot

Использование:
    from payments import get_payment_provider
    provider = get_payment_provider("telegram_stars")
    invoice = await provider.create_invoice(amount=100, currency="XTR", ...)
"""

from payments.base import BasePaymentProvider, PaymentInvoice, PaymentResult

__all__ = ["BasePaymentProvider", "PaymentInvoice", "PaymentResult"]
