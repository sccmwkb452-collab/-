from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    bot_token: str
    bot_admin_ids: list[int] = Field(default_factory=list)

    webhook_host: str = ""
    webhook_path: str = "/webhook"
    webhook_port: int = 8443

    # ── Database ──────────────────────────────────────────────────────────────
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "nft_gifts"
    postgres_user: str = "nft_user"
    postgres_password: str

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""

    # ── Application ───────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    debug_sql: bool = False

    # ── Payments ──────────────────────────────────────────────────────────────
    payments_provider_token: str = ""
    cryptobot_api_token: str = ""
    cryptobot_api_url: str = "https://pay.crypt.bot/api"

    # ── Subscriptions ─────────────────────────────────────────────────────────
    sub_basic_price_stars: int = 100
    sub_premium_price_stars: int = 300
    sub_basic_duration_days: int = 30
    sub_premium_duration_days: int = 30

    # ── Support ───────────────────────────────────────────────────────────────
    support_username: str = "support_bot"

    # ── Computed ──────────────────────────────────────────────────────────────
    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def database_url_sync(self) -> str:
        """Используется только Alembic."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @computed_field
    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_host}{self.webhook_path}" if self.webhook_host else ""

    @field_validator("bot_admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
