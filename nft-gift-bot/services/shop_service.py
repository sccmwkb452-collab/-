"""
Shop service: order creation, TON payment verification, delivery.

Security invariants:
- Orders never delivered before on-chain payment confirmed.
- Double-spend: unique tx_hash + SELECT FOR UPDATE on order row.
- Double-delivery: SELECT FOR UPDATE on deliver_order; checks status == PAID.
- Products only visible when is_verified=True AND status=ACTIVE.
- encrypted_delivery_info never returned until delivery is confirmed.
"""
import logging
import random
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models.shop import DeliveryType, OrderStatus, ProductStatus, ShopOrder, ShopProduct
from database.repositories.bot_setting_repo import BotSettingRepository
from database.repositories.shop_repo import ShopOrderRepository, ShopProductRepository
from payments.ton.client import TonCenterClient
from payments.ton.verifier import TonPaymentVerifier
from services.crypto_service import decrypt_session

logger = logging.getLogger(__name__)

SETTING_SHOP_PRICE_TON = "shop_price_ton"
SETTING_SHOP_PAYMENT_WINDOW_MINUTES = "shop_payment_window_minutes"
DEFAULT_SHOP_PRICE_TON = 5.0
DEFAULT_PAYMENT_WINDOW_MINUTES = 60


def _make_order_comment() -> str:
    digits = "".join(random.choices(string.digits, k=8))
    return f"SHP{digits}"


@dataclass
class OrderInitResult:
    order: ShopOrder
    amount_ton: float
    recipient_address: str
    payment_comment: str
    expires_at: datetime


@dataclass
class OrderCheckResult:
    paid: bool
    reason: str


@dataclass
class DeliverResult:
    success: bool
    reason: str
    delivery_payload: str | None = None  # only for SECURE_TOKEN type after delivery


class ShopService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._product_repo = ShopProductRepository(session)
        self._order_repo = ShopOrderRepository(session)
        self._setting_repo = BotSettingRepository(session)

    async def _get_price(self) -> float:
        raw = await self._setting_repo.get(SETTING_SHOP_PRICE_TON)
        try:
            if raw:
                return float(raw)
        except ValueError:
            pass
        return DEFAULT_SHOP_PRICE_TON

    async def _get_window_minutes(self) -> int:
        raw = await self._setting_repo.get(SETTING_SHOP_PAYMENT_WINDOW_MINUTES)
        if raw and raw.isdigit():
            return int(raw)
        return DEFAULT_PAYMENT_WINDOW_MINUTES

    async def set_shop_price(self, price_ton: float) -> None:
        await self._setting_repo.set(SETTING_SHOP_PRICE_TON, str(price_ton))

    # Alias used by admin router
    async def set_default_price(self, price_ton: float) -> None:
        await self.set_shop_price(price_ton)

    async def get_catalog(self) -> list[ShopProduct]:
        return await self._product_repo.get_catalog()

    async def get_product(self, product_id: int) -> ShopProduct | None:
        return await self._product_repo.get_by_id(product_id)

    async def create_order(self, user_id: int, product_id: int) -> OrderInitResult | None:
        """
        Create a PENDING order for the user.
        Returns None if product is unavailable.
        Reuses existing valid PENDING order if one exists.
        """
        product = await self._product_repo.get_by_id(product_id)
        if not product or product.status != ProductStatus.ACTIVE or not product.is_verified:
            return None
        if product.stock <= 0:
            return None

        # Reuse existing pending order if still valid
        existing = await self._order_repo.get_pending_for_user_and_product(user_id, product_id)
        if existing:
            return OrderInitResult(
                order=existing,
                amount_ton=float(existing.amount_ton),
                recipient_address=settings.ton_recipient_address,
                payment_comment=existing.payment_comment,
                expires_at=existing.expires_at,
            )

        price = await self._get_price()
        window_minutes = await self._get_window_minutes()
        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(minutes=window_minutes)
        comment = _make_order_comment()

        order = await self._order_repo.create(
            user_id=user_id,
            product_id=product_id,
            payment_comment=comment,
            amount_ton=price,
            expires_at=expires_at,
        )
        await self._order_repo.add_log(order.id, f"Order created for user {user_id}")
        logger.info("Shop order created: order_id=%d user=%d comment=%s", order.id, user_id, comment)

        return OrderInitResult(
            order=order,
            amount_ton=price,
            recipient_address=settings.ton_recipient_address,
            payment_comment=comment,
            expires_at=expires_at,
        )

    async def check_and_pay(self, payment_comment: str) -> OrderCheckResult:
        """
        Verify TON payment on-chain and mark order as PAID.

        NEVER marks PAID on user message, screenshot, or button press alone.
        Requires real blockchain confirmation via TonPaymentVerifier.
        Double-spend protected by SELECT FOR UPDATE + unique tx_hash constraint.
        """
        order = await self._order_repo.get_by_comment_for_update(payment_comment)
        if not order:
            return OrderCheckResult(paid=False, reason="Заказ не найден.")

        if order.status == OrderStatus.PAID:
            return OrderCheckResult(paid=True, reason="Оплата уже подтверждена.")

        if order.status != OrderStatus.PENDING:
            return OrderCheckResult(
                paid=False, reason=f"Заказ в статусе {order.status.value}, оплата невозможна."
            )

        now = datetime.now(tz=timezone.utc)
        if order.expires_at < now:
            order.status = OrderStatus.CANCELLED
            await self._order_repo.add_log(order.id, "Order expired before payment")
            return OrderCheckResult(paid=False, reason="Время оплаты истекло.")

        client = TonCenterClient(
            api_key=settings.toncenter_api_key,
            network=settings.ton_network,
        )
        verifier = TonPaymentVerifier(
            client=client,
            recipient_address=settings.ton_recipient_address,
            required_ton=float(order.amount_ton),
        )
        result = await verifier.verify(payment_comment)

        if not result.ok:
            return OrderCheckResult(paid=False, reason=result.reason or "Транзакция не найдена.")

        tx_hash = result.tx.tx_hash if result.tx else None
        if tx_hash and await self._order_repo.tx_hash_exists(tx_hash):
            return OrderCheckResult(paid=False, reason="Эта транзакция уже использована.")

        # Lock product for stock decrement
        product = await self._product_repo.get_for_update(order.product_id)
        if not product or product.stock <= 0:
            return OrderCheckResult(paid=False, reason="Товар закончился.")

        product.stock -= 1
        if product.stock == 0:
            product.status = ProductStatus.SOLD_OUT

        order.status = OrderStatus.PAID
        order.paid_at = now
        order.tx_hash = tx_hash
        await self._order_repo.add_log(
            order.id, f"Payment confirmed on-chain tx={tx_hash}"
        )
        logger.info(
            "Shop order paid: order_id=%d tx=%s product_id=%d",
            order.id, tx_hash, order.product_id,
        )
        return OrderCheckResult(paid=True, reason="Оплата подтверждена!")

    async def deliver_order(self, order_id: int, admin_id: int) -> DeliverResult:
        """
        Mark order as DELIVERED. Admin-only.

        SELECT FOR UPDATE prevents double-delivery.
        For SECURE_TOKEN products, decrypts and returns payload once.
        """
        order = await self._order_repo.get_for_update(order_id)
        if not order:
            return DeliverResult(success=False, reason="Заказ не найден.")

        if order.status == OrderStatus.DELIVERED:
            return DeliverResult(success=False, reason="Заказ уже выдан.")

        if order.status != OrderStatus.PAID:
            return DeliverResult(
                success=False,
                reason=f"Нельзя выдать заказ в статусе {order.status.value}. Требуется статус PAID.",
            )

        delivery_payload: str | None = None
        product = order.product

        if product and product.delivery_type == DeliveryType.SECURE_TOKEN:
            if product.encrypted_delivery_info and settings.account_encryption_key:
                try:
                    delivery_payload = decrypt_session(
                        product.encrypted_delivery_info,
                        settings.account_encryption_key,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to decrypt delivery info for product %d: %s",
                        product.id, exc,
                    )
                    return DeliverResult(success=False, reason="Ошибка расшифровки данных товара.")

        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(tz=timezone.utc)
        await self._order_repo.add_log(order.id, f"Delivered by admin {admin_id}")
        logger.info("Shop order delivered: order_id=%d by admin=%d", order_id, admin_id)

        return DeliverResult(success=True, reason="Заказ выдан.", delivery_payload=delivery_payload)

    async def admin_verify_product(
        self, product_id: int, admin_id: int, note: str
    ) -> tuple[bool, str]:
        """
        Mark product as verified and set status to ACTIVE.

        REQUIRED before product appears in catalog. The note must document
        lawful ownership and permitted transfer method.
        """
        product = await self._product_repo.get_by_id(product_id)
        if not product:
            return False, "Товар не найден."
        if product.status == ProductStatus.DELETED:
            return False, "Товар удалён."

        product.is_verified = True
        product.verified_by_admin_id = admin_id
        product.verification_note = note
        product.status = ProductStatus.ACTIVE
        logger.info(
            "Product verified: id=%d admin=%d note=%r", product_id, admin_id, note
        )
        return True, "Товар верифицирован и опубликован."

    async def admin_get_all_products(self) -> list[ShopProduct]:
        return await self._product_repo.get_all_admin()

    async def admin_set_stock(self, product_id: int, stock: int) -> tuple[bool, str]:
        product = await self._product_repo.get_by_id(product_id)
        if not product:
            return False, "Товар не найден."
        if product.status == ProductStatus.DELETED:
            return False, "Товар удалён."
        product.stock = stock
        if stock > 0 and product.status == ProductStatus.SOLD_OUT and product.is_verified:
            product.status = ProductStatus.ACTIVE
        elif stock == 0 and product.status == ProductStatus.ACTIVE:
            product.status = ProductStatus.SOLD_OUT
        return True, f"Остаток установлен: {stock}"

    async def admin_disable_product(self, product_id: int) -> tuple[bool, str]:
        product = await self._product_repo.get_by_id(product_id)
        if not product or product.status == ProductStatus.DELETED:
            return False, "Товар не найден."
        product.status = ProductStatus.INACTIVE
        return True, "Товар снят с продажи."

    async def admin_enable_product(self, product_id: int) -> tuple[bool, str]:
        product = await self._product_repo.get_by_id(product_id)
        if not product or product.status == ProductStatus.DELETED:
            return False, "Товар не найден."
        if not product.is_verified:
            return False, "Товар не верифицирован. Сначала выполните /shop verify."
        product.status = ProductStatus.ACTIVE if product.stock > 0 else ProductStatus.SOLD_OUT
        return True, "Товар опубликован."

    async def admin_delete_product(self, product_id: int) -> tuple[bool, str]:
        product = await self._product_repo.get_by_id(product_id)
        if not product:
            return False, "Товар не найден."
        product.status = ProductStatus.DELETED
        return True, "Товар удалён (мягко)."

    async def admin_get_paid_orders(self) -> list[ShopOrder]:
        return await self._order_repo.get_pending_orders_admin()

    async def expire_old_pending(self) -> int:
        return await self._order_repo.expire_old_pending()

    # Alias used by scheduler
    async def expire_old_orders(self) -> int:
        return await self.expire_old_pending()
