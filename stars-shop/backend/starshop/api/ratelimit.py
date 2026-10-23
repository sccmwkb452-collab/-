"""Fixed-window rate limiter. Uses Redis when REDIS_URL is set (shared
between API workers), otherwise an in-process dict (single worker/dev)."""

from __future__ import annotations

import time

from ..config import get_settings
from ..shared.errors import RateLimited

try:  # optional dependency at runtime
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[assignment,misc]


class RateLimiter:
    def __init__(self) -> None:
        self._redis = None
        self._memory: dict[str, tuple[int, float]] = {}
        url = get_settings().redis_url
        if url and Redis is not None:
            self._redis = Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)

    async def hit(self, key: str, limit: int, window: int) -> bool:
        """Count one request; return False when the limit is exceeded."""
        if not get_settings().rate_limit_enabled:
            return True
        bucket = int(time.time() // window)
        full_key = f"rl:{key}:{bucket}"
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(full_key)
                pipe.expire(full_key, window + 1)
                count, _ = await pipe.execute()
                return int(count) <= limit
            except Exception:
                pass  # Redis down: degrade to local limiting instead of failing requests
        count, expires = self._memory.get(full_key, (0, time.time() + window))
        count += 1
        self._memory[full_key] = (count, expires)
        if len(self._memory) > 50_000:
            now = time.time()
            self._memory = {k: v for k, v in self._memory.items() if v[1] > now}
        return count <= limit

    async def check(self, key: str, limit: int, window: int = 60) -> None:
        if not await self.hit(key, limit, window):
            raise RateLimited()

    async def ping(self) -> bool | None:
        if self._redis is None:
            return None
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def reset_limiter() -> None:
    global _limiter
    _limiter = None
