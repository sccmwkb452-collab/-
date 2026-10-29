"""Импорт экспорта из любого парсера: CSV или JSON.

Подходит для парсер-ботов и сервисов без API: выгрузите результаты в файл и
отправьте его боту в разделе «🔎 Парсеры».
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from typing import Any

from app.ai.state import normalize_currency, to_decimal
from app.parsers.base import Candidate, ParserAdapter, ParserError, SearchCriteria

MAX_ROWS = 5000
ALIASES = {
    "telegram_user_id": ("telegram_user_id", "user_id", "tg_id", "telegram_id", "id"),
    "username": ("username", "user", "login", "tg", "telegram"),
    "display_name": ("name", "display_name", "full_name", "first_name", "имя"),
    "role": ("role", "type", "роль", "тип"),
    "text": ("text", "description", "notes", "bio", "описание", "комментарий"),
    "price": ("price", "цена"),
    "currency": ("currency", "валюта"),
    "geo": ("geo", "city", "country", "location", "город", "страна"),
    "source_url": ("url", "link", "source_url", "ссылка"),
}


def parse_import_file(data: bytes, filename: str) -> list[dict[str, Any]]:
    name = filename.lower()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251")
    if name.endswith(".json"):
        payload = json.loads(text)
        rows = payload.get("items", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ParserError("JSON должен быть списком объектов или {\"items\": [...]}")
        rows = [r for r in rows if isinstance(r, dict)]
    elif name.endswith((".csv", ".txt")):
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    else:
        raise ParserError("Поддерживаются файлы .csv и .json")
    if len(rows) > MAX_ROWS:
        raise ParserError(f"В файле больше {MAX_ROWS} строк — разделите его")
    return rows


def _pick(row: dict[str, Any], field: str) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in ALIASES[field]:
        value = lowered.get(alias)
        if value not in (None, ""):
            return value
    return None


def normalize_row(raw: dict[str, Any]) -> Candidate | None:
    """Строка экспорта/API → Candidate (общий формат для импорта и HTTP API)."""
    uid = _pick(raw, "telegram_user_id")
    username = _pick(raw, "username")
    if isinstance(username, str):
        username = username.strip().lstrip("@").split("/")[-1].lower() or None
    try:
        uid = int(uid) if uid is not None else None
    except (TypeError, ValueError):
        uid = None
    external = str(uid or username or raw.get("external_id") or "")
    if not external:
        return None
    known = {a for aliases in ALIASES.values() for a in aliases}
    attributes = {str(k): v for k, v in raw.items() if str(k).strip().lower() not in known and v not in (None, "")}
    role = (_pick(raw, "role") or "").strip().lower() or None
    role = {"продавец": "seller", "покупатель": "buyer"}.get(role, role)
    return Candidate(
        external_id=external, telegram_user_id=uid, username=username,
        display_name=_pick(raw, "display_name"), role=role, text=_pick(raw, "text"),
        attributes=attributes, price=to_decimal(_pick(raw, "price")),
        currency=normalize_currency(_pick(raw, "currency")), geo=_pick(raw, "geo"),
        source_url=_pick(raw, "source_url"),
    )


class FileImportAdapter(ParserAdapter):
    key = "file_import"
    title = "Импорт файла (CSV/JSON)"
    description = "Результаты любого парсера, выгруженные в файл"

    async def validate(self) -> tuple[bool, str]:
        rows = self.config.import_rows or []
        if not rows:
            return False, "Файл ещё не загружен"
        return True, f"Загружено строк: {len(rows)}"

    async def search(self, criteria: SearchCriteria) -> AsyncIterator[dict[str, Any]]:
        for row in (self.config.import_rows or [])[: criteria.max_results]:
            yield row

    def normalize_result(self, raw: dict[str, Any]) -> Candidate | None:
        return normalize_row(raw)
