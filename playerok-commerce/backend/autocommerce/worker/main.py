"""Background worker: scheduler + job queue + notification sender.

One long-running process (see deploy/). Several workers may run: jobs are
claimed with SKIP LOCKED and periodic jobs are deduplicated by key, so the
same work never runs twice. On start, jobs left RUNNING by a crashed worker
are put back in the queue.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import ensure_startup_config, get_settings
from ..database.enums import SupplierOrderStatus
from ..database.models import Product, SupplierOrder
from ..database.session import dispose_engine, session_scope
from ..logging_setup import setup_logging
from ..services import (
    app_settings,
    fx,
    health,
    jobs,
    listings,
    messages,
    notifications,
    orders,
    reports,
    repricing,
    research,
    retention,
    suppliers,
)
from ..services.notifications import esc
from ..shared.timeutil import local_tz, utcnow

log = logging.getLogger("autocommerce.worker")
Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[Any]]


async def _reprice_all(session: AsyncSession, _: dict) -> int:
    products = (await session.execute(select(Product))).unique().scalars().all()
    for product in products:
        await repricing.reprice_product(session, product)
    return len(products)


async def _poll_supplier_orders(session: AsyncSession, _: dict) -> int:
    rows = (
        (
            await session.execute(
                select(SupplierOrder)
                .where(SupplierOrder.status.in_([SupplierOrderStatus.PENDING, SupplierOrderStatus.UNKNOWN, SupplierOrderStatus.CREATED]))
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    for so in rows:
        before = so.status
        await suppliers.poll(session, so)
        if before is not so.status and so.status is SupplierOrderStatus.UNKNOWN:
            await notifications.notify(
                session,
                "supplier_error",
                "Закупка с неизвестным результатом",
                f"Заказ поставщику #{so.id}: ответ не получен. Проверьте в кабинете поставщика — автоматический повтор запрещён.\n{esc(so.last_error or '')}",
                dedupe_key=f"so_unknown:{so.id}",
            )
    return len(rows)


async def _reprice_one(session: AsyncSession, payload: dict) -> Any:
    from ..services.catalog import get_product

    return await repricing.reprice_product(session, await get_product(session, int(payload["product_id"])))


async def _check_suppliers(session: AsyncSession, _: dict) -> dict:
    return await suppliers.check_all(session)


async def _sync_suppliers(session: AsyncSession, _: dict) -> int:
    return len(await suppliers.sync_all(session))


HANDLERS: dict[str, Handler] = {
    "order.process": lambda s, p: orders.process(s, int(p["order_id"])),
    "order.poll": lambda s, p: orders.poll(s, int(p["order_id"])),
    "order.reminder": lambda s, p: orders.send_reminder(s, int(p["order_id"]), p["kind"], int(p.get("n", 1))),
    "message.ignore_check": lambda s, p: messages.ignore_check(s, int(p["message_id"])),
    "product.reprice": lambda s, p: _reprice_one(s, p),
    "products.reprice_all": _reprice_all,
    "fx.sync": lambda s, p: fx.sync_cbr(s),
    "suppliers.sync": _sync_suppliers,
    "suppliers.check": _check_suppliers,
    "suppliers.poll_orders": _poll_supplier_orders,
    "research.recompute": lambda s, p: research.recompute_all(s),
    "retention.cleanup": lambda s, p: retention.cleanup(s),
    "report.daily": lambda s, p: reports.send_daily(s),
    "report.weekly": lambda s, p: reports.send_weekly(s),
    "autolisting.run": lambda s, p: listings.auto_listing_run(s),
    "autoraise.remind": lambda s, p: listings.raise_reminder(s),
}


async def _run_handler(kind: str, session: AsyncSession, payload: dict) -> Any:
    return await HANDLERS[kind](session, payload)


# periodic jobs: kind -> (every N minutes)
PERIODIC: dict[str, int] = {
    "fx.sync": 360,
    "suppliers.sync": 30,
    "suppliers.check": 60,
    "suppliers.poll_orders": 5,
    "products.reprice_all": 60,
    "research.recompute": 360,
    "retention.cleanup": 1440,
    "autolisting.run": 60,
}


def _slot(now: datetime, minutes: int) -> str:
    epoch_minutes = int(now.timestamp() // 60)
    return str(epoch_minutes // minutes)


async def schedule(session: AsyncSession, now: datetime | None = None) -> int:
    """Enqueue periodic jobs whose time slot started. Dedupe keys include the
    slot number, so restarting or running two workers does not duplicate them."""
    now = now or utcnow()
    count = 0
    for kind, minutes in PERIODIC.items():
        if await jobs.enqueue(session, kind, {}, dedupe_key=f"sched:{kind}:{_slot(now, minutes)}", max_attempts=3):
            count += 1
    from ..services.autosettings import is_active

    active, cfg = await is_active(session, "auto_raise")
    if active and await jobs.enqueue(
        session, "autoraise.remind", {}, dedupe_key=f"sched:autoraise:{_slot(now, int(cfg['interval_minutes']))}"
    ):
        count += 1
    local = now.astimezone(local_tz())
    daily = await app_settings.get_setting(session, "reports.daily")
    if daily["enabled"] and local.hour >= int(daily["hour"]):
        if await jobs.enqueue(session, "report.daily", {}, dedupe_key=f"sched:report.daily:{local.date().isoformat()}", max_attempts=3):
            count += 1
    weekly = await app_settings.get_setting(session, "reports.weekly")
    if weekly["enabled"] and local.isoweekday() == int(weekly["weekday"]) and local.hour >= int(weekly["hour"]):
        if await jobs.enqueue(session, "report.weekly", {}, dedupe_key=f"sched:report.weekly:{local.date().isoformat()}", max_attempts=3):
            count += 1
    return count


class Worker:
    def __init__(self, worker_id: str | None = None) -> None:
        self.settings = get_settings()
        self.worker_id = worker_id or health.INSTANCE
        self.stopping = asyncio.Event()
        self.started_at = utcnow()
        self.processed = 0
        self.failed = 0
        self._last = {"beat": 0.0, "schedule": 0.0, "recover": 0.0}

    async def run_job_batch(self) -> int:
        async with session_scope() as session:
            claimed = await jobs.claim(session, self.worker_id, limit=self.settings.worker_concurrency)
            claimed_ids = [(j.id, j.kind, dict(j.payload)) for j in claimed]
        for job_id, kind, payload in claimed_ids:
            await self.execute(job_id, kind, payload)
        return len(claimed_ids)

    async def execute(self, job_id: int, kind: str, payload: dict) -> None:
        from ..database.models import AutomationJob

        error: str | None = None
        retry = True
        try:
            if kind not in HANDLERS:
                raise LookupError(f"unknown job kind {kind}")
            async with session_scope() as session:
                await _run_handler(kind, session, payload)
        except LookupError as exc:
            error, retry = str(exc), False
        except Exception as exc:  # noqa: BLE001 - every job failure is recorded and retried
            error = f"{type(exc).__name__}: {exc}"
            log.exception("job failed", extra={"job_id": job_id, "kind": kind})
        async with session_scope() as session:
            job = await session.get(AutomationJob, job_id, with_for_update=True)
            if job is None:
                return
            if error is None:
                await jobs.complete(session, job)
                self.processed += 1
            else:
                will_retry = await jobs.fail(session, job, error, retry=retry)
                self.failed += 1
                if not will_retry and kind.startswith(("order.", "suppliers.")):
                    await notifications.notify(
                        session,
                        "system",
                        f"Фоновая задача не выполнена: {kind}",
                        f"Попыток: {job.attempts}. Ошибка: {esc(error[:500])}",
                        dedupe_key=f"job_failed:{job_id}",
                    )

    async def tick(self) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()
        if now - self._last["recover"] > 60:
            async with session_scope() as session:
                recovered = await jobs.recover_stale(session)
            if recovered:
                log.warning("recovered stale jobs", extra={"count": recovered})
            self._last["recover"] = now
        if now - self._last["schedule"] > 30:
            async with session_scope() as session:
                await schedule(session)
            self._last["schedule"] = now
        await self.run_job_batch()
        async with session_scope() as session:
            await notifications.send_pending(session)
        if now - self._last["beat"] > 30:
            await health.beat("worker", {"processed": self.processed, "failed": self.failed}, started_at=self.started_at)
            self._last["beat"] = now

    async def run(self) -> None:
        log.info("worker started", extra={"worker": self.worker_id})
        backoff = 1.0
        while not self.stopping.is_set():
            try:
                await self.tick()
                backoff = 1.0
            except Exception:  # noqa: BLE001 - e.g. database temporarily unavailable
                log.exception("worker tick failed; retrying")
                backoff = min(60.0, backoff * 2)
                await asyncio.sleep(backoff)
                continue
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=self.settings.worker_poll_seconds)
            except TimeoutError:
                pass
        log.info("worker stopped")


async def main() -> None:
    setup_logging("worker")
    ensure_startup_config("worker")
    worker = Worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stopping.set)
    try:
        await worker.run()
    finally:
        await dispose_engine()


def run() -> None:
    asyncio.run(main())
