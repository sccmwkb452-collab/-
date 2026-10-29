"""Подключаемый LLM-клиент. Реализация по умолчанию — Claude (Anthropic API).

Все вызовы возвращают JSON по схеме (structured outputs), поэтому код агента
работает со структурированными решениями, а не разбирает свободный текст.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Ошибка, которую бессмысленно повторять (неверный запрос, ответ не по схеме)."""


class LLMUnavailable(LLMError):
    """Временная недоступность (сеть, 429, 5xx) — можно повторить позже."""


class LLMRefusal(LLMError):
    """Модель отказалась отвечать по соображениям безопасности."""


class LLMNotConfigured(LLMError):
    """API-ключ не задан."""


@dataclass(slots=True)
class ImageInput:
    data: bytes
    media_type: str = "image/jpeg"

    def to_block(self) -> dict[str, Any]:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": self.media_type,
                "data": base64.standard_b64encode(self.data).decode("ascii"),
            },
        }


class LLMClient(Protocol):
    async def generate_json(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        schema: dict[str, Any],
        effort: str | None = None,
    ) -> dict[str, Any]: ...


class AnthropicLLM:
    """Claude через официальный SDK `anthropic`.

    - structured outputs (`output_config.format`) — ответ всегда валидный JSON по схеме;
    - серверные fallbacks при отказе модели (`fallbacks="default"`), если включены;
    - системный промпт кэшируется (prompt caching), т.к. он стабилен между запросами.
    """

    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-5-5",
        effort: str = "medium",
        max_tokens: int = 16000,
        server_fallbacks: bool = True,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        if not api_key and client is None:
            raise LLMNotConfigured("ANTHROPIC_API_KEY не задан")
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.server_fallbacks = server_fallbacks

    async def generate_json(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        schema: dict[str, Any],
        effort: str | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "effort": effort or self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        if self.server_fallbacks:
            kwargs["betas"] = [self.FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        try:
            response = await self._client.beta.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMNotConfigured(f"Ключ Anthropic отклонён: {exc.message}") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Некорректный запрос к ИИ: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMUnavailable("Лимит запросов к ИИ, повторите позже") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"ИИ недоступен: HTTP {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable("Нет соединения с API ИИ") from exc

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise LLMRefusal(f"Модель отказалась отвечать (категория: {category})")
        if response.stop_reason == "max_tokens":
            raise LLMError("Ответ ИИ обрезан по max_tokens")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("ИИ не вернул текстовый блок")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("ИИ вернул невалидный JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("ИИ вернул JSON не-объект")
        return data


def build_llm(settings) -> LLMClient | None:
    """None, если ключ не задан: агент тогда не отвечает и сообщает владельцу почему."""
    if not settings.anthropic_api_key:
        return None
    return AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.ai_model,
        effort=settings.ai_effort,
        max_tokens=settings.ai_max_tokens,
        server_fallbacks=settings.ai_server_fallbacks,
    )
