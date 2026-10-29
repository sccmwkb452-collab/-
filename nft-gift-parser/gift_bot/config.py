"""Настройки бота из переменных окружения."""
import os
from dataclasses import dataclass

DEFAULT_ADMIN_ID = 8790784360


@dataclass(slots=True)
class Config:
    token: str
    admin_ids: frozenset[int]
    db_path: str
    concurrency: int
    proxy: str | None


def load_dotenv(path: str = ".env") -> None:
    """Строки KEY=VALUE из .env; переменные окружения важнее файла."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_config() -> Config:
    load_dotenv()
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Укажи токен: BOT_TOKEN=... python bot.py")
    raw_admins = os.environ.get("ADMIN_IDS", str(DEFAULT_ADMIN_ID))
    admins = frozenset(int(x) for x in raw_admins.replace(" ", "").split(",") if x)
    return Config(
        token=token,
        admin_ids=admins,
        db_path=os.environ.get("DB_PATH", "gifts.db"),
        concurrency=int(os.environ.get("PARSE_CONCURRENCY", "5")),
        proxy=os.environ.get("PARSE_PROXY") or None,
    )
