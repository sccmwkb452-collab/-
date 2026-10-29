"""Внешний парсер с HTTP API.

Контракт (его реализует сервис парсера):
  GET {resource}/health                 → 200
  GET {resource}/search?role=&q=&geo=&limit=&cursor=&filters=<json>
      → {"items": [{"id"|"user_id", "username", "name", "role", "text", "price", "currency", "geo", "url", ...}],
         "next": "<cursor>|null"}
  GET {resource}/profiles/{id}          → объект профиля или 404
Токен: переменная окружения PARSER_TOKEN_<ИМЯ_ПАРСЕРА> → заголовок Authorization: Bearer.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from app.config import get_parser_token
from app.parsers.base import Candidate, ParserAdapter, ParserError, SearchCriteria
from app.parsers.file_import import normalize_row


class HttpApiAdapter(ParserAdapter):
    key = "http_api"
    title = "HTTP API парсера"
    description = "Сервис парсера с API по документированному контракту"

    def __init__(self, config, session: aiohttp.ClientSession | None = None) -> None:
        super().__init__(config)
        self.base = (config.resource or "").rstrip("/")
        self._session = session
        self._own = session is None

    def _headers(self) -> dict[str, str]:
        token = get_parser_token(self.config.name)
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def connect(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
        await self.connect()
        try:
            async with self._session.get(self.base + path, params=params, headers=self._headers()) as resp:
                body = await resp.json(content_type=None) if resp.status == 200 else None
                return resp.status, body
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ParserError(f"парсер недоступен: {exc}") from exc

    async def validate(self) -> tuple[bool, str]:
        if not self.base.startswith(("https://", "http://")):
            return False, "Укажите URL API парсера"
        try:
            status, _ = await self._get("/health")
        except ParserError as exc:
            return False, str(exc)
        if status == 401 or status == 403:
            return False, f"Доступ запрещён: задайте токен в PARSER_TOKEN_{self.config.name.upper()}"
        return (status == 200, "API доступно" if status == 200 else f"/health вернул HTTP {status}")

    async def search(self, criteria: SearchCriteria) -> AsyncIterator[dict[str, Any]]:
        cursor, seen = None, 0
        while seen < criteria.max_results:
            params = {
                "role": criteria.target_role, "q": " ".join(criteria.keywords), "geo": criteria.geo or "",
                "limit": min(100, criteria.max_results - seen), "filters": json.dumps(criteria.filters, ensure_ascii=False),
            }
            if cursor:
                params["cursor"] = cursor
            status, body = await self._get("/search", params)
            if status != 200 or not isinstance(body, dict):
                raise ParserError(f"/search вернул HTTP {status}")
            items = body.get("items") or []
            for item in items:
                seen += 1
                yield item
            cursor = body.get("next")
            if not cursor or not items:
                return

    async def fetch_profile(self, external_id: str) -> dict[str, Any] | None:
        status, body = await self._get(f"/profiles/{external_id}")
        return body if status == 200 else None

    def normalize_result(self, raw: dict[str, Any]) -> Candidate | None:
        return normalize_row(raw)

    async def disconnect(self) -> None:
        if self._own and self._session is not None:
            await self._session.close()
            self._session = None
