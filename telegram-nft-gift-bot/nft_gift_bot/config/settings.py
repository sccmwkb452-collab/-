"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["test", "production"] = "test"
    log_level: str = "INFO"

    bot_token: SecretStr = SecretStr("")
    # Comma-separated Telegram user IDs. Only these IDs get admin rights.
    admin_ids: str = ""

    database_url: str = "postgresql+asyncpg://nft_bot:nft_bot@localhost:5432/nft_bot"

    # Fernet key used to encrypt sensitive values (Business connection IDs etc.).
    encryption_key: SecretStr = SecretStr("")

    # TON payments
    ton_receiver_address: str = ""
    ton_api_url: str = "https://toncenter.com/api/v2"
    ton_api_key: SecretStr = SecretStr("")
    subscription_price_ton: Decimal = Decimal("10")
    subscription_days: int = 30
    payment_ttl_minutes: int = 30
    payment_poll_seconds: int = 30
    subscription_check_seconds: int = 600
    expiry_warning_hours: int = 72

    # Gifts
    transfer_confirm_ttl_seconds: int = 300

    # Anti-abuse
    rate_limit_per_minute: int = 30

    @property
    def admin_id_set(self) -> frozenset[int]:
        ids: set[int] = set()
        for part in self.admin_ids.split(","):
            part = part.strip()
            if part:
                if not part.isdigit():
                    raise ValueError(f"ADMIN_IDS must contain numeric Telegram IDs only, got {part!r}")
                ids.add(int(part))
        return frozenset(ids)

    def validate_runtime(self) -> None:
        """Fail fast on missing secrets instead of failing later in a handler."""
        if not self.bot_token.get_secret_value():
            raise RuntimeError("BOT_TOKEN is not set")
        if not self.encryption_key.get_secret_value():
            raise RuntimeError("ENCRYPTION_KEY is not set (generate with scripts/generate_key.py)")
        if self.environment == "production" and not self.ton_receiver_address:
            raise RuntimeError("TON_RECEIVER_ADDRESS must be set in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
