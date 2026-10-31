"""Конфигурация из переменных окружения (.env).

Секреты (токены, API-ключи) задаются только здесь — бот никогда не
запрашивает их в переписке.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent

# Главный администратор по ТЗ. Можно расширить через ADMIN_IDS.
DEFAULT_ADMIN_ID = 8790784360


def _parse_ids(value: object) -> list[int]:
    if value is None or value == "":
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [int(x) for x in value.replace(";", ",").split(",") if x.strip().lstrip("-").isdigit()]
    if isinstance(value, (list, tuple)):
        return [int(x) for x in value]
    raise ValueError(f"Не удалось разобрать список ID: {value!r}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────────────────
    bot_token: str = ""
    # Строкой, чтобы pydantic-settings не пытался разбирать "1,2" как JSON.
    admin_ids_raw: str = Field(default=str(DEFAULT_ADMIN_ID), alias="ADMIN_IDS")
    # Кто ещё может пользоваться панелью и подключать Business. Пусто — только админы.
    allowed_user_ids_raw: str = Field(default="", alias="ALLOWED_USER_IDS")

    # ── Storage ───────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://agent:agent@db:5432/agent"
    redis_url: str = ""  # пусто — FSM в памяти, без Redis
    media_dir: Path = ROOT_DIR / "storage" / "media"

    # ── AI ────────────────────────────────────────────────────────────────
    # Провайдер: auto — Anthropic, если задан ANTHROPIC_API_KEY, иначе OpenAI.
    ai_provider: Literal["auto", "anthropic", "openai"] = "auto"
    anthropic_api_key: str = ""
    # Свой адрес Anthropic-совместимого API (посредник). Пусто — официальный api.anthropic.com.
    ai_base_url: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5-mini"
    ai_model: str = "claude-opus-5-5"
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    ai_max_tokens: int = 16000
    ai_server_fallbacks: bool = True

    # ── Media ─────────────────────────────────────────────────────────────
    ffmpeg_path: str = "ffmpeg"
    media_max_frames: int = 6
    # Bot API отдаёт файлы до 20 МБ; больше — честно сообщаем об ограничении.
    media_max_download_bytes: int = 20 * 1024 * 1024

    # ── Crypto Pay (@CryptoBot) ───────────────────────────────────────────
    crypto_pay_api_token: str = ""
    crypto_pay_network: Literal["mainnet", "testnet"] = "mainnet"

    # ── HTTP-парсеры: токены по имени парсера, PARSER_TOKEN_<NAME> ─────────
    # Читаются через get_parser_token(), здесь не перечисляются.

    # ── Application ───────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_json: bool = False
    scheduler_interval_seconds: int = 30
    reply_delay_seconds: float = 4.0

    @property
    def llm_provider(self) -> str | None:
        if self.ai_provider == "anthropic":
            return "anthropic" if self.anthropic_api_key else None
        if self.ai_provider == "openai":
            return "openai" if self.openai_api_key else None
        if self.anthropic_api_key:
            return "anthropic"
        return "openai" if self.openai_api_key else None

    @property
    def llm_model(self) -> str:
        return self.openai_model if self.llm_provider == "openai" else self.ai_model

    @property
    def admin_ids(self) -> list[int]:
        return _parse_ids(self.admin_ids_raw)

    @property
    def allowed_user_ids(self) -> list[int]:
        return _parse_ids(self.allowed_user_ids_raw)

    @field_validator("admin_ids_raw", "allowed_user_ids_raw", mode="before")
    @classmethod
    def _ids_to_str(cls, v: object) -> str:
        return ",".join(str(i) for i in _parse_ids(v))

    @field_validator("log_level")
    @classmethod
    def _level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Неизвестный LOG_LEVEL: {v}")
        return v

    def is_admin(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and telegram_id in self.admin_ids

    def can_use_panel(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and (
            telegram_id in self.admin_ids or telegram_id in self.allowed_user_ids
        )


def get_parser_token(parser_name: str) -> str:
    """Токен HTTP-парсера из окружения: PARSER_TOKEN_<NAME> (имя в верхнем регистре)."""
    import os

    key = "PARSER_TOKEN_" + "".join(c if c.isalnum() else "_" for c in parser_name).upper()
    return os.environ.get(key, "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
