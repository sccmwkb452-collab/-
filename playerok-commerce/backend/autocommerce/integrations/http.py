"""Shared HTTP client helpers: timeouts, retries with exponential backoff for
transient errors only, and secret-free error messages."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from ..config import get_settings
from ..shared.masking import scrub_text

log = logging.getLogger(__name__)
T = TypeVar("T")

USER_AGENT = "PlayerOK-Auto-Commerce/1.0 (+self-hosted seller tool)"
TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


class IntegrationError(Exception):
    """Error talking to an external service. ``transient`` errors may be retried;
    ``uncertain`` means the remote side may have executed the request."""

    def __init__(self, message: str, *, transient: bool = False, uncertain: bool = False, status: int | None = None):
        super().__init__(scrub_text(message))
        self.transient = transient
        self.uncertain = uncertain
        self.status = status


_transport_override: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Route every integration client through ``transport`` (tests use httpx.MockTransport)."""
    global _transport_override
    _transport_override = transport


def client(base_url: str = "", headers: dict[str, str] | None = None, timeout: float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout or get_settings().http_timeout_seconds,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        follow_redirects=False,
        transport=_transport_override,
    )


async def with_retries(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Retry *read-only* calls on transient errors. Never wrap purchases with this."""
    last: IntegrationError | None = None
    for attempt in range(attempts):
        try:
            return await func()
        except IntegrationError as exc:
            if not exc.transient or attempt == attempts - 1:
                raise
            last = exc
            delay = base_delay * (2**attempt) * (1 + random.random() * 0.25)
            log.info("transient integration error, retrying", extra={"attempt": attempt + 1, "delay": round(delay, 2), "error": str(exc)})
            await sleep(delay)
    raise last or IntegrationError("retry failed")  # pragma: no cover


def classify(exc: Exception, *, mutating: bool = False) -> IntegrationError:
    """Map httpx errors. For mutating calls a timeout after sending is uncertain."""
    if isinstance(exc, IntegrationError):
        return exc
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return IntegrationError(f"нет соединения: {type(exc).__name__}", transient=True)
    if isinstance(exc, httpx.TimeoutException):
        return IntegrationError("таймаут ответа", transient=not mutating, uncertain=mutating)
    if isinstance(exc, httpx.HTTPError):
        return IntegrationError(f"ошибка HTTP: {type(exc).__name__}", transient=not mutating, uncertain=mutating)
    return IntegrationError(f"{type(exc).__name__}: {exc}")


def check_status(response: httpx.Response, *, mutating: bool = False) -> None:
    if response.status_code < 400:
        return
    transient = response.status_code in TRANSIENT_STATUS
    body = response.text[:300]
    raise IntegrationError(
        f"HTTP {response.status_code}: {body}",
        transient=transient and not mutating,
        uncertain=mutating and response.status_code >= 500,
        status=response.status_code,
    )
