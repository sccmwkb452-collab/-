import logging
import sys
from pathlib import Path

from bot.config import settings

LOGS_DIR = Path(__file__).parent.parent / "logs"


def setup_logging() -> None:
    LOGS_DIR.mkdir(exist_ok=True)

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "bot.log", encoding="utf-8"),
    ]

    for handler in handlers:
        handler.setFormatter(logging.Formatter(fmt, datefmt))

    logging.basicConfig(
        level=log_level,
        handlers=handlers,
    )

    # Reduce noise from third-party libs
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.debug else logging.WARNING
    )
