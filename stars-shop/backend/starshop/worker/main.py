"""Background worker: delivery, notifications, payment reconciliation,
refunds and expiry of unpaid orders.

Run: ``python -m starshop.worker``. Safe to run several instances.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from ..database.enums import ActorType, OrderStatus, PaymentStatus
from ..database.models import Order, Payment
from ..database.session import dispose_engine, session_scope
from ..delivery import service as delivery
from ..logging_setup import setup_logging
from ..notifications.sender import TelegramSender, send_due
from ..payments import service as payments
from ..payments.registry import get_payment_provider
from ..services.app_settings import load_runtime_settings
from ..services.orders import cancel_order
from ..shared.errors import AppError
from ..shared.timeutil import utcnow

log = logging.getLogger("starshop.worker")
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/starshop-worker.heartbeat"))
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


async def delivery_tick() -> int:
    async with session_scope() as session:
        ids = await delivery.claim_due(session, WORKER_ID)
    for task_id in ids:
        try:
            result = await delivery.process_task(task_id)
            log.info("delivery processed", extra={"task_id": str(task_id), "result": result})
        except Exception:
            log.exception("delivery task failed", extra={"task_id": str(task_id)})
    async with session_scope() as session:
        await delivery.recover_stale(session)
    return len(ids)


async def notification_tick(sender: TelegramSender) -> int:
    async with session_scope() as session:
        return await send_due(session, sender)


async def reconcile_tick() -> int:
    """Ask providers about open payments in case a webhook was lost."""
    now = utcnow()
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(Payment.id)
                    .where(
                        Payment.status == PaymentStatus.pending,
                        Payment.is_demo.is_(False),
                        Payment.provider_payment_id.is_not(None),
                        Payment.updated_at < now - timedelta(seconds=45),
                        Payment.created_at > now - timedelta(days=2),
                    )
                    .order_by(Payment.updated_at)
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
    for payment_id in rows:
        try:
            async with session_scope() as session:
                runtime = await load_runtime_settings(session)
                payment = await session.get(Payment, payment_id)
                if payment is None:
                    continue
                payment.updated_at = utcnow()  # rotate through the queue
                await payments.reconcile(session, payment, runtime)
        except AppError as exc:
            log.warning("reconcile failed", extra={"payment_id": str(payment_id), "error": exc.message})
        except Exception:
            log.exception("reconcile crashed", extra={"payment_id": str(payment_id)})
    return len(rows)


async def expiry_tick() -> int:
    now = utcnow()
    async with session_scope() as session:
        ids = (
            (
                await session.execute(
                    select(Order.id)
                    .where(Order.status.in_((OrderStatus.created, OrderStatus.pending_payment)), Order.expires_at < now)
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
    for order_id in ids:
        try:
            async with session_scope() as session:
                runtime = await load_runtime_settings(session)
                order = await session.get(Order, order_id)
                if order is None:
                    continue
                # Last chance: maybe it was paid and the webhook is late.
                try:
                    if await payments.reconcile_order(session, order, runtime, source="expiry") == "confirmed":
                        continue
                except AppError:
                    pass
                await session.refresh(order)
                if order.status not in (OrderStatus.created, OrderStatus.pending_payment):
                    continue
                stale = await cancel_order(
                    session,
                    order,
                    runtime,
                    actor_type=ActorType.system,
                    actor_id=None,
                    reason="Время на оплату истекло",
                    event_type="order_expired",
                )
            for payment in stale:
                try:
                    await get_payment_provider(payment.provider).cancel(payment)
                except Exception:
                    log.warning("provider cancel failed", extra={"payment_id": str(payment.id)})
        except Exception:
            log.exception("expiry failed", extra={"order_id": str(order_id)})
    return len(ids)


async def refund_tick() -> int:
    async with session_scope() as session:
        ids = (
            (
                await session.execute(
                    select(Payment.id).where(Payment.status == PaymentStatus.refund_pending, Payment.refund_next_at <= utcnow()).limit(10)
                )
            )
            .scalars()
            .all()
        )
    for payment_id in ids:
        try:
            async with session_scope() as session:
                runtime = await load_runtime_settings(session)
                result = await payments.process_refund(session, payment_id, runtime)
            log.info("refund processed", extra={"payment_id": str(payment_id), "result": result})
        except Exception:
            log.exception("refund crashed", extra={"payment_id": str(payment_id)})
    return len(ids)


async def _loop(name: str, interval: float, fn: Callable[[], Awaitable[int]], stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await fn()
        except Exception:
            log.exception("loop iteration failed", extra={"loop": name})
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass


async def _heartbeat(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(HEARTBEAT.write_text, str(int(utcnow().timestamp())))
        try:
            await asyncio.wait_for(stop.wait(), timeout=10)
        except TimeoutError:
            pass


async def main() -> None:
    setup_logging("worker")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    sender = TelegramSender()
    log.info("worker started", extra={"worker_id": WORKER_ID})
    try:
        await asyncio.gather(
            _heartbeat(stop),
            _loop("delivery", 2, delivery_tick, stop),
            _loop("notifications", 1, lambda: notification_tick(sender), stop),
            _loop("reconcile", 30, reconcile_tick, stop),
            _loop("expiry", 30, expiry_tick, stop),
            _loop("refunds", 15, refund_tick, stop),
        )
    finally:
        await sender.close()
        await dispose_engine()
        log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
