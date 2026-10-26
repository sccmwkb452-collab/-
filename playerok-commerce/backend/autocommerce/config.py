"""Application configuration.

Secrets (bot token, supplier keys, encryption keys) come from the environment
only and are wrapped in ``SecretStr`` so they never appear in logs, API
responses or ``repr()``. Supplier keys entered in the web panel are stored
encrypted in ``integration_credentials``; environment values take precedence.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]

# libpq options that hosting providers put into URLs, as asyncpg names them
# (None: asyncpg has no such option).
_ASYNCPG_URL_OPTIONS: dict[str, str | None] = {"sslmode": "ssl", "channel_binding": None}

DEV_SECRET = "dev-secret-key-change-me-dev-secret-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    # --- runtime -----------------------------------------------------------
    app_env: Literal["development", "production", "test"] = "development"
    # Initial operations mode. "test": purchases and publications are never
    # executed for real. "live" is accepted only with allow_live_operations.
    app_mode: Literal["test", "live"] = "test"
    allow_live_operations: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    display_timezone: str = "Europe/Moscow"
    base_currency: str = "RUB"

    # --- web / api ---------------------------------------------------------
    web_base_url: str = "http://localhost:3000"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Number of reverse proxies in front of the API whose X-Forwarded-For is trusted
    # (Vercel rewrite + Caddy = 2). 0 — use the socket address.
    trusted_proxy_hops: int = 0
    secret_key: SecretStr = SecretStr(DEV_SECRET)
    # Fernet key (urlsafe base64, 32 bytes) for credentials and digital codes.
    # Generate: python -m autocommerce.cli gen-key
    credentials_key: SecretStr = SecretStr("")
    session_hours: int = 12
    session_idle_minutes: int = 120
    login_max_attempts: int = 5
    login_lock_minutes: int = 15
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 300

    # --- storage -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://pac:pac@localhost:5432/pac"
    database_pool_size: int = 10
    redis_url: str | None = None
    storage_dir: Path = BACKEND_DIR / "storage"
    assets_dir: Path = BACKEND_DIR / "assets"

    # --- telegram ----------------------------------------------------------
    bot_token: SecretStr = SecretStr("")
    bot_username: str = ""
    owner_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    telegram_api_base: str = "https://api.telegram.org"
    # Seconds a revealed digital code stays in the chat before the bot deletes it.
    code_reveal_ttl_seconds: int = 120

    # --- worker ------------------------------------------------------------
    worker_poll_seconds: float = 2.0
    worker_concurrency: int = 4
    worker_job_lease_seconds: int = 300

    # --- suppliers -----------------------------------------------------------
    vexboost_api_url: str = "https://vexboost.ru/api/v2"
    vexboost_api_key: SecretStr = SecretStr("")
    reloadly_client_id: SecretStr = SecretStr("")
    reloadly_client_secret: SecretStr = SecretStr("")
    reloadly_sandbox: bool = True
    fragment_base_url: str = "https://fragment.com"
    fragment_min_interval_minutes: int = 30
    cbr_daily_url: str = "https://www.cbr.ru/scripts/XML_daily.asp"
    http_timeout_seconds: float = 20.0

    # --- data retention ----------------------------------------------------
    retention_logs_days: int = 180
    retention_messages_days: int = 365
    retention_notifications_days: int = 90

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: str) -> str:
        """Accept plain postgres:// URLs (Neon, Supabase, Railway): use the
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("owner_telegram_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(item) for item in value.replace(";", ",").split(",") if item.strip()]
        if isinstance(value, int):
            return [value]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.app_env == "production"

    def config_problems(self) -> list[str]:
        """Human readable problems that block a production start."""
        problems: list[str] = []
        if self.is_production:
            if self.secret_key.get_secret_value() == DEV_SECRET or len(self.secret_key.get_secret_value()) < 32:
                problems.append("SECRET_KEY не задан или короче 32 символов")
            if not self.credentials_key.get_secret_value():
                problems.append("CREDENTIALS_KEY не задан (python -m autocommerce.cli gen-key)")
            if not self.web_base_url.startswith("https://"):
                problems.append("WEB_BASE_URL должен начинаться с https://")
        if self.app_mode == "live" and not self.allow_live_operations:
            problems.append("APP_MODE=live требует ALLOW_LIVE_OPERATIONS=true")
        return problems


@lru_cache
def get_settings() -> Settings:
    # PAC_ENV_FILE="" disables reading .env (tests must never pick up real secrets)
    env_file = os.environ.get("PAC_ENV_FILE", ".env")
    return Settings(_env_file=env_file or None)  # type: ignore[call-arg]


def ensure_startup_config(service: str) -> None:
    """Refuse to start a long-running service with a configuration that is unsafe
    for production (default SECRET_KEY, no encryption key, live mode not allowed)."""
    problems = get_settings().config_problems()
    if problems:
        raise SystemExit(f"{service}: запуск остановлен, исправьте конфигурацию:\n- " + "\n- ".join(problems))


def reset_settings_cache() -> None:
    get_settings.cache_clear()
