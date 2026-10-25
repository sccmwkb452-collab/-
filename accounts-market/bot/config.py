"""Application settings loaded from environment / .env.

Secrets (bot token, payment keys) live only here and are never logged.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr = Field(default=SecretStr(""))
    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")

    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://market:market@localhost:5432/market"
    redis_url: str | None = None

    # Initial value for the shop name; afterwards it is edited in the admin panel.
    shop_name: str = "ACCOUNTS MARKET"

    # Payments
    payment_provider: Literal["demo", "cryptopay", "yookassa"] = "demo"
    demo_mode: bool = False
    payment_ttl_minutes: int = 60
    payment_poll_seconds: int = 30
    max_topup_rub: int = 100_000

    cryptopay_token: SecretStr = Field(default=SecretStr(""))
    cryptopay_testnet: bool = False
    cryptopay_accepted_assets: str = "USDT,TON,BTC"

    yookassa_shop_id: str = ""
    yookassa_secret_key: SecretStr = Field(default=SecretStr(""))
    yookassa_return_url: str = ""

    # HTTP server for payment webhooks and health checks
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    @field_validator("redis_url", mode="before")
    @classmethod
    def _empty_redis(cls, value: str | None) -> str | None:
        return value or None

    @property
    def admin_ids(self) -> frozenset[int]:
        ids: set[int] = set()
        for part in self.admin_ids_raw.replace(";", ",").split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                ids.add(int(part))
        return frozenset(ids)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _guard_demo(self) -> "Settings":
        if self.payment_provider == "demo" and self.is_production:
            raise ValueError(
                "PAYMENT_PROVIDER=demo is not allowed with ENVIRONMENT=production: "
                "configure cryptopay or yookassa"
            )
        if self.payment_provider == "demo" and not self.demo_mode:
            raise ValueError("PAYMENT_PROVIDER=demo requires DEMO_MODE=true")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
