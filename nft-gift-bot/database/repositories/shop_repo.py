from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.shop import OrderStatus, ProductStatus, ShopOrder, ShopOrderLog, ShopProduct


class ShopProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, product_id: int) -> ShopProduct | None:
        return await self._session.get(ShopProduct, product_id)

    async def get_for_update(self, product_id: int) -> ShopProduct | None:
        result = await self._session.execute(
            select(ShopProduct).where(ShopProduct.id == product_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[ShopProduct]:
        result = await self._session.execute(
            select(ShopProduct)
            .where(
                ShopProduct.status == ProductStatus.active,
                ShopProduct.is_verified.is_(True),
                ShopProduct.stock > 0,
            )
            .order_by(ShopProduct.id)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[ShopProduct]:
        result = await self._session.execute(
            select(ShopProduct)
            .where(ShopProduct.status != ProductStatus.deleted)
            .order_by(ShopProduct.id)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ShopProduct:  # type: ignore[override]
        obj = ShopProduct(**kwargs)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def save(self, obj: ShopProduct) -> ShopProduct:
        self._session.add(obj)
        await self._session.flush()
        return obj


class ShopOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **kwargs) -> ShopOrder:  # type: ignore[override]
        obj = ShopOrder(**kwargs)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def get_for_update(self, order_id: int) -> ShopOrder | None:
        result = await self._session.execute(
            select(ShopOrder).where(ShopOrder.id == order_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_comment_for_update(self, comment: str) -> ShopOrder | None:
        result = await self._session.execute(
            select(ShopOrder).where(ShopOrder.payment_comment == comment).with_for_update()
        )
        return result.scalar_one_or_none()

    async def tx_hash_exists(self, tx_hash: str) -> bool:
        result = await self._session.execute(
            select(ShopOrder.id).where(ShopOrder.tx_hash == tx_hash)
        )
        return result.scalar_one_or_none() is not None

    async def get_pending_for_user(self, user_id: int, product_id: int) -> ShopOrder | None:
        result = await self._session.execute(
            select(ShopOrder)
            .where(
                ShopOrder.user_id == user_id,
                ShopOrder.product_id == product_id,
                ShopOrder.status == OrderStatus.pending,
            )
            .order_by(ShopOrder.id.desc())
        )
        return result.scalars().first()

    async def list_for_user(self, user_id: int, limit: int = 20) -> list[ShopOrder]:
        result = await self._session.execute(
            select(ShopOrder)
            .where(ShopOrder.user_id == user_id)
            .order_by(ShopOrder.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def expire_old_pending(self) -> int:
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            update(ShopOrder)
            .where(
                ShopOrder.status == OrderStatus.pending,
                ShopOrder.expires_at < now,
            )
            .values(status=OrderStatus.cancelled)
            .returning(ShopOrder.id)
        )
        rows = result.fetchall()
        return len(rows)

    async def log(self, order_id: int, event: str) -> None:
        entry = ShopOrderLog(
            order_id=order_id,
            event=event,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(entry)
        await self._session.flush()
