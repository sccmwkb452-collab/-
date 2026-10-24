"""Background jobs without a worker process (``INLINE_WORKER=true``, serverless).

After an API request the instance runs the jobs that are due, each at most
once per interval; after a request that may have changed something (a
payment, a refund, an admin action) the urgent ones run right away, so a DEMO
purchase is delivered as soon as it is paid. The jobs are those of
``main.py`` and are safe to run in several instances at once.
"""

from __future__ import annotations

import logging
import time

from ..config import get_settings
from ..notifications.sender import TelegramSender
from . import main as jobs

log = logging.getLogger("starshop.worker")

# Seconds between runs in one instance.
INTERVALS = {"delivery": 2.0, "notifications": 2.0, "refunds": 15.0, "expiry": 30.0, "reconcile": 30.0}
URGENT = {"delivery", "notifications", "refunds"}
_last_run: dict[str, float] = {}


async def _notifications() -> int:
    sender = TelegramSender()
    try:
        return await jobs.notification_tick(sender)
    finally:
        await sender.close()


JOBS = {
    "delivery": jobs.delivery_tick,
    "notifications": _notifications,
    "refunds": jobs.refund_tick,
    "expiry": jobs.expiry_tick,
    "reconcile": jobs.reconcile_tick,
}


async def run_due(*, after_change: bool = False) -> None:
    now = time.monotonic()
    sends_messages = bool(get_settings().bot_token.get_secret_value())
    for name, job in JOBS.items():
        if name == "notifications" and not sends_messages:
            continue
        urgent = after_change and name in URGENT
        if not urgent and now - _last_run.get(name, float("-inf")) < INTERVALS[name]:
            continue
        _last_run[name] = now  # before awaiting, so a concurrent request skips the job
        try:
            await job()
        except Exception:
            log.exception("inline job failed", extra={"job": name})


def reset() -> None:
    """Forget the last runs (tests)."""
    _last_run.clear()
