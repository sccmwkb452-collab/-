"""Реестр адаптеров и определение способа подключения источника."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.db.models import ParserConfig
from app.parsers.base import ParserAdapter
from app.parsers.file_import import FileImportAdapter
from app.parsers.http_api import HttpApiAdapter
from app.parsers.nft_owners import NftOwnersAdapter, parse_collection

ADAPTERS: dict[str, type[ParserAdapter]] = {
    FileImportAdapter.key: FileImportAdapter,
    NftOwnersAdapter.key: NftOwnersAdapter,
    HttpApiAdapter.key: HttpApiAdapter,
}


@dataclass
class Detection:
    adapter: str | None
    explanation: str


def detect_source(resource: str) -> Detection:
    r = (resource or "").strip()
    if re.search(r"t\.me/nft/", r, re.I):
        return Detection("nft_owners", "Ссылка на NFT-подарок: будут просмотрены публичные страницы коллекции.")
    bot = re.fullmatch(r"(?:@|(?:https?://)?t\.me/)([A-Za-z0-9_]{4,32})/?", r)
    if bot:
        name = bot.group(1)
        if name.lower().endswith("bot"):
            return Detection(
                "file_import",
                f"@{name} — Telegram-бот. Боты не могут получать данные от других ботов через Bot API, поэтому "
                "напрямую подключить его нельзя. Выгрузите результаты из @{0} в CSV/JSON и отправьте файл сюда.".format(name),
            )
        return Detection(None, f"@{name} — это аккаунт или канал, а не источник данных парсера.")
    if r.startswith(("http://", "https://")):
        return Detection("http_api", "URL сервиса: будет использован HTTP API по контракту (см. README).")
    if parse_collection(r):
        return Detection("nft_owners", f"Похоже на коллекцию NFT-подарков «{r}».")
    return Detection(None, "Не удалось определить источник. Укажите URL API, ссылку t.me/nft/… или загрузите файл.")


def build_adapter(cfg: ParserConfig) -> ParserAdapter:
    cls = ADAPTERS.get(cfg.adapter)
    if cls is None:
        raise ValueError(f"Неизвестный адаптер парсера: {cfg.adapter}")
    return cls(cfg)
