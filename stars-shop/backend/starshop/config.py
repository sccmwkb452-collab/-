"""Application configuration.

Everything secret (bot token, payment keys, supplier keys) comes from the
environment only and is wrapped in ``SecretStr`` so it never lands in logs,
API responses or ``repr()`` output. Brand defaults live here too; the admin
panel can override the public-facing ones at runtime (see ``services.settings``).
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# libpq options in the URLs that hosting providers hand out, as asyncpg spells them
# (None: asyncpg has no such option).
_ASYNCPG_URL_OPTIONS: dict[str, str | None] = {"sslmode": "ssl", "channel_binding": None}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- runtime -----------------------------------------------------------
    app_env: Literal["development", "production", "test"] = "development"
    # Initial shop mode. The owner can switch it in the admin panel, but
    # production can only be enabled when ``allow_production`` is true.
    app_mode: Literal["demo", "production"] = "demo"
    allow_production: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    display_timezone: str = "Europe/Moscow"

    public_base_url: str = "http://localhost:5173"
    webapp_path: str = "/"
    admin_path: str = "/admin/"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    secret_key: SecretStr = SecretStr("change-me-in-production-please-32+chars")

    # --- storage -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://stars:stars@localhost:5432/stars"
    # 0 turns pooling off: a serverless instance keeps no connections between requests.
    database_pool_size: int = 10
    redis_url: str | None = None

    # --- serverless hosting (Vercel, see docs/VERCEL.md) -------------------
    # Public DEMO site: visitors outside Telegram get an anonymous identity
    # (shared/demo_identity.py). It works only while the shop is in DEMO mode
    # and never opens the admin panel.
    public_demo: bool = False
    # Background jobs run after API requests instead of in a worker process.
    inline_worker: bool = False
    # The first request of each instance applies the migrations, creates the
    # demo catalog in a new database and the admins from ADMIN_TELEGRAM_IDS.
    auto_migrate: bool = False

    # --- telegram ----------------------------------------------------------
    bot_token: SecretStr = SecretStr("")
    bot_username: str = ""
    # Short name of the Mini App registered in @BotFather (/newapp). Optional:
    # when set, deep links use https://t.me/<bot>/<app>?startapp=...
    webapp_short_name: str = ""
    bot_mode: Literal["polling", "webhook"] = "polling"
    bot_webhook_secret: SecretStr = SecretStr("")
    bot_webhook_path: str = "/tg/webhook"
    bot_webhook_port: int = 8081
    telegram_api_base: str = "https://api.telegram.org"
    init_data_max_age_seconds: int = 24 * 3600
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    # Development-only helper that signs fake initData so the Mini App can be
    # opened in a regular browser. Refused unless app_env == development.
    dev_auth_enabled: bool = False

    # --- brand defaults (overridable from the admin panel) ------------------
    brand_name: str = "Pulsar"
    brand_tagline: str = "Telegram Stars без лишних шагов"
    shop_currency: str = "RUB"
    support_telegram: str = ""
    support_email: str = ""

    # --- orders ------------------------------------------------------------
    order_payment_ttl_minutes: int = 30
    max_open_orders_per_user: int = 5

    # --- payments ----------------------------------------------------------
    # Comma separated list of enabled payment providers: demo, cryptopay
    payment_providers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["demo"])
    cryptopay_api_token: SecretStr = SecretStr("")
    cryptopay_network: Literal["mainnet", "testnet"] = "testnet"
    cryptopay_accepted_assets: str = "USDT,TON,BTC"
    cryptopay_verify_via_api: bool = True

    # --- delivery ----------------------------------------------------------
    # demo | manual | http_supplier
    delivery_provider: Literal["demo", "manual", "http_supplier"] = "demo"
    # Telegram Premium orders; empty — the same as DELIVERY_PROVIDER.
    premium_delivery_provider: Literal["", "demo", "manual", "http_supplier", "telegram_premium"] = ""
    delivery_min_stars: int = 50
    delivery_max_stars: int = 1_000_000
    delivery_max_attempts: int = 5
    supplier_api_url: str = ""
    supplier_api_key: SecretStr = SecretStr("")
    supplier_api_secret: SecretStr = SecretStr("")
    supplier_timeout_seconds: float = 20.0

    # --- rate limiting -----------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_per_ip_per_minute: int = 240

    # --- admin -------------------------------------------------------------
    admin_session_hours: int = 12
    admin_login_token_minutes: int = 5

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: str) -> str:
        """Accept plain postgres:// URLs (Neon, Supabase, Heroku): use the
        asyncpg driver and its names for the connection options."""
        scheme, sep, rest = value.partition("://")
        if scheme in ("postgres", "postgresql"):
            scheme = "postgresql+asyncpg"
        location, _, query = rest.partition("?")
        if scheme != "postgresql+asyncpg" or not query:
            return f"{scheme}{sep}{rest}"
        options = []
        for key, item in parse_qsl(query, keep_blank_values=True):
            name = _ASYNCPG_URL_OPTIONS.get(key, key)
            if name is not None:
                options.append((name, item))
        return f"{scheme}://{location}" + (f"?{urlencode(options)}" if options else "")

    @field_validator("cors_origins", "payment_providers", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(item) for item in value.replace(" ", "").split(",") if item]
        if isinstance(value, int):
            return [value]
        return value

    @field_validator("shop_currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("shop_currency must be an ISO 4217 code, e.g. RUB")
        return value

    # --- derived -----------------------------------------------------------
    @property
    def is_production_env(self) -> bool:
        return self.app_env == "production"

    @property
    def webapp_url(self) -> str:
        return self.public_base_url.rstrip("/") + self.webapp_path

    @property
    def admin_url(self) -> str:
        return self.public_base_url.rstrip("/") + self.admin_path

    @property
    def cryptopay_api_base(self) -> str:
        if self.cryptopay_network == "mainnet":
            return "https://pay.crypt.bot/api"
        return "https://testnet-pay.crypt.bot/api"

    @property
    def money_quantum(self) -> Decimal:
        return Decimal("0.01")


@lru_cache
def get_settings() -> Settings:
    return Settings()
