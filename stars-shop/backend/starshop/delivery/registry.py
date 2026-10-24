from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .base import DeliveryProvider
from .demo import DemoDeliveryProvider
from .http_supplier import HttpSupplierDeliveryProvider
from .manual import ManualDeliveryProvider
from .telegram_premium import TelegramPremiumDeliveryProvider

_override: dict[str, DeliveryProvider] = {}


@lru_cache
def _build(name: str) -> DeliveryProvider:
    settings = get_settings()
    if name == "demo":
        provider: DeliveryProvider = DemoDeliveryProvider()
    elif name == "manual":
        provider = ManualDeliveryProvider()
    elif name == "http_supplier":
        provider = HttpSupplierDeliveryProvider(settings)
    elif name == "telegram_premium":
        provider = TelegramPremiumDeliveryProvider(settings)
    else:
        raise KeyError(name)
    # Order size limits of the delivery channel (Fragment: from 50 Stars).
    provider.min_stars = settings.delivery_min_stars
    provider.max_stars = settings.delivery_max_stars
    return provider


def get_delivery_provider(name: str | None = None) -> DeliveryProvider:
    name = name or get_settings().delivery_provider
    if name in _override:
        return _override[name]
    return _build(name)


def get_premium_delivery_provider() -> DeliveryProvider:
    """Telegram Premium can go through its own channel (PREMIUM_DELIVERY_PROVIDER)."""
    return get_delivery_provider(get_settings().premium_delivery_provider or None)


def override_provider(provider: DeliveryProvider) -> None:
    """Test hook."""
    _override[provider.name] = provider


def reset_overrides() -> None:
    _override.clear()
    _build.cache_clear()
