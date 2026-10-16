"""Background asyncio tasks: payment expiry + subscription expiry + shop order expiry."""
import asyncio
import logging

from database.session import AsyncSessionFactory
from payments.payment_service import PaymentService
from services.shop_service import ShopService
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

PAYMENT_CHECK_INTERVAL = 30    # seconds
EXPIRY_CHECK_INTERVAL = 3600   # seconds (1 hour)
SHOP_ORDER_CHECK_INTERVAL = 300  # seconds (5 minutes)


async def _expire_payments_loop() -> None:
    while True:
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    count = await PaymentService(session).expire_old_pending()
            if count:
                logger.info("Scheduler: expired %d pending TON payment(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler: error in expire_payments_loop")
        await asyncio.sleep(PAYMENT_CHECK_INTERVAL)


async def _expire_subscriptions_loop() -> None:
    while True:
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    count = await SubscriptionService(session).expire_outdated()
            if count:
                logger.info("Scheduler: expired %d subscription(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler: error in expire_subscriptions_loop")
        await asyncio.sleep(EXPIRY_CHECK_INTERVAL)


async def _expire_shop_orders_loop() -> None:
    while True:
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    count = await ShopService(session).expire_old_orders()
            if count:
                logger.info("Scheduler: expired %d pending shop order(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler: error in expire_shop_orders_loop")
        await asyncio.sleep(SHOP_ORDER_CHECK_INTERVAL)


def start_scheduler() -> list[asyncio.Task]:
    tasks = [
        asyncio.create_task(_expire_payments_loop(), name="expire_payments"),
        asyncio.create_task(_expire_subscriptions_loop(), name="expire_subscriptions"),
        asyncio.create_task(_expire_shop_orders_loop(), name="expire_shop_orders"),
    ]
    logger.info("Scheduler started: %d tasks", len(tasks))
    return tasks


def stop_scheduler(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    logger.info("Scheduler tasks cancelled")
