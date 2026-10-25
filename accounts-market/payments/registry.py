from __future__ import annotations

from bot.config import Settings
from payments.base import PaymentProvider


def build_provider(settings: Settings, bot_username: str = "") -> PaymentProvider:
    if settings.payment_provider == "cryptopay":
        from payments.cryptopay import CryptoPayProvider

        return CryptoPayProvider(
            settings.cryptopay_token.get_secret_value(),
            testnet=settings.cryptopay_testnet,
            assets=settings.cryptopay_accepted_assets,
        )
    if settings.payment_provider == "yookassa":
        from payments.yookassa import YooKassaProvider

        return YooKassaProvider(
            settings.yookassa_shop_id,
            settings.yookassa_secret_key.get_secret_value(),
            settings.yookassa_return_url or f"https://t.me/{bot_username}",
        )
    from payments.demo import DemoProvider

    return DemoProvider()
