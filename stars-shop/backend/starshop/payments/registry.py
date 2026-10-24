from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from ..shared.errors import NotFound
from .base import PaymentProvider
from .cryptopay import CryptoPayProvider
from .demo import DemoPaymentProvider
from .telegram_stars import TelegramStarsProvider

_override: dict[str, PaymentProvider] = {}

KNOWN_PROVIDERS = ("demo", "cryptopay", "telegram_stars")


@lru_cache
def _build(name: str) -> PaymentProvider:
    settings = get_settings()
    if name == "demo":
        return DemoPaymentProvider(settings)
    if name == "cryptopay":
        return CryptoPayProvider(settings)
    if name == "telegram_stars":
        return TelegramStarsProvider(settings)
    raise NotFound("Неизвестный платёжный провайдер", code="unknown_provider")


def get_payment_provider(name: str) -> PaymentProvider:
    if name in _override:
        return _override[name]
    if name not in KNOWN_PROVIDERS:
        raise NotFound("Неизвестный платёжный провайдер", code="unknown_provider")
    return _build(name)


def enabled_providers(mode: str, currency: str | None = None) -> list[PaymentProvider]:
    """Providers a customer may choose right now for a price in ``currency``
    (the shop currency by default). The DEMO provider exists only in DEMO
    mode; real providers must be configured."""
    settings = get_settings()
    currency = currency or settings.shop_currency
    result = []
    for name in settings.payment_providers:
        if name not in KNOWN_PROVIDERS and name not in _override:
            continue
        provider = get_payment_provider(name)
        if provider.is_demo and mode != "demo":
            continue
        if not provider.is_configured() or not provider.accepts(currency, settings.shop_currency):
            continue
        result.append(provider)
    return result


def override_provider(provider: PaymentProvider) -> None:
    _override[provider.name] = provider


def reset_overrides() -> None:
    _override.clear()
    _build.cache_clear()
