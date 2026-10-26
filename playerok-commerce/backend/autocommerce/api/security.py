"""Request helpers: client IP behind trusted proxies, rate limiting, CSRF."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict, deque

from fastapi import Request

from ..config import get_settings
from ..shared.errors import TooManyRequests

SESSION_COOKIE = "pac_session"
CSRF_COOKIE = "pac_csrf"
CSRF_HEADER = "x-csrf-token"


def client_ip(request: Request) -> str:
    hops = get_settings().trusted_proxy_hops
    forwarded = request.headers.get("x-forwarded-for", "")
    if hops > 0 and forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[max(0, len(parts) - hops)]
    return request.client.host if request.client else "unknown"


def csrf_token_for(session_token: str) -> str:
    secret = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(secret, f"csrf:{session_token}".encode(), hashlib.sha256).hexdigest()


def csrf_ok(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    header = request.headers.get(CSRF_HEADER, "")
    return bool(token) and hmac.compare_digest(header, csrf_token_for(token))


class RateLimiter:
    """Sliding window in process memory (one API instance). For several
    instances put a shared limiter (Redis) in front."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float) -> None:
        if not get_settings().rate_limit_enabled:
            return
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry = int(window - (now - bucket[0])) + 1
            raise TooManyRequests(f"Слишком много запросов. Повторите через {retry} с", details={"retry_after": retry})
        bucket.append(now)
        if len(self.hits) > 50_000:  # memory guard
            self.hits.clear()


limiter = RateLimiter()


def reset_limiter() -> None:
    limiter.hits.clear()
