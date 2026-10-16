from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    # Telegram
    bot_token: str
    bot_admin_ids: List[int] = []

    # Database
    database_url: str

    # App
    debug: bool = False
    log_level: str = "INFO"

    # Support
    support_username: str = "support"

    @field_validator("bot_admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
