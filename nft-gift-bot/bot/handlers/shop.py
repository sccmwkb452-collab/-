"""Shop handlers: catalog, product card, order creation, payment check, my orders."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.shop_kb import (
    catalog_kb,
    empty_catalog_kb,
    my_orders_kb,
    order_payment_kb,
    product_kb,
)
from bot.ui.rich_text import RichTextBuilder
from database.models.user import User
from services.shop_service import ShopService

logger = logging.getLogger(__name__)
router = Router(name="shop")

_STATUS_LABELS = {
    "pending": "⏳ Ожидает оплаты",
    "paid": "✅ Оплачен",
    "delivered": "📦 Выдан",
    "cancelled": "❌ Отменён",
    "refunded": "↩️ Возврат",
}


@router.callback_query(F.data.in_({"tdata:shop", "shop:catalog"}))
async def cb_catalog(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    products = await ShopService(session).get_catalog()

    rt = RichTextBuilder()
    rt.bold("🛒 Магазин\n\n")

    if not products:
        rt.text("В магазине пока нет доступных товаров.\n")
        rt.text("Загляни позже!")
        t, e = rt.build()
        await callback.message.edit_text(text=t, entities=e, reply_markup=empty_catalog_kb())
        return

    rt.text(f"Доступно товаров: {len(products)}\n")
    rt.text("Выбери товар из списка ниже:")
    t, e = rt.build()
    await callback.message.edit_text(text=t, entities=e, reply_markup=catalog_kb(products))


@router.callback_query(F.data.startswith("shop:product:"))
async def cb_product(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    product_id = int(callback.data.removeprefix("shop:product:"))
    service = ShopService(session)
    product = await service.get_product(product_id)

    if not product or not product.is_verified:
        await callback.answer("Товар недоступен.", show_alert=True)
        return

    rt = RichTextBuilder()
    rt.bold(f"{product.title}\n\n")
    if product.description:
        rt.text(f"{product.description}\n\n")
    rt.bold("Цена: ")
    rt.text(f"{float(product.price_ton):.2f} TON\n")
    rt.bold("Наличие: ")
    rt.text(f"{product.stock} шт.\n")
    t, e = rt.build()
    await callback.message.edit_text(text=t, entities=e, reply_markup=product_kb(product_id))


@router.callback_query(F.data.startswith("shop:buy:"))
async def cb_buy(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    product_id = int(callback.data.removeprefix("shop:buy:"))
    service = ShopService(session)

    init = await service.create_order(db_user.id, product_id)
    await session.commit()

    if not init:
        rt = RichTextBuilder()
        rt.bold("❌ Товар недоступен\n\n")
        rt.text("Товар закончился или снят с продажи.")
        t, e = rt.build()
        await callback.message.edit_text(
            text=t, entities=e, reply_markup=empty_catalog_kb()
        )
        return

    rt = RichTextBuilder()
    rt.bold("💳 Оплата заказа\n\n")
    rt.bold("Товар: ")
    rt.text(f"{init.order.product.title}\n")
    rt.bold("Сумма: ")
    rt.text(f"{init.amount_ton:.2f} TON\n\n")
    rt.bold("Адрес кошелька:\n")
    rt.text(f"{init.recipient_address}\n\n")
    rt.bold("Комментарий к переводу (обязательно!):\n")
    rt.text(f"{init.payment_comment}\n\n")
    rt.text("⚠️ Переведи точную сумму с указанным комментарием.\n")
    rt.text("После перевода нажми кнопку ниже для проверки.")

    expires_str = init.expires_at.strftime("%H:%M %d.%m.%Y UTC")
    rt.text(f"\n\n⏰ Действует до: {expires_str}")
    t, e = rt.build()
    await callback.message.edit_text(
        text=t, entities=e, reply_markup=order_payment_kb(init.payment_comment)
    )
    logger.info(
        "Shop order payment screen shown: user_id=%d product_id=%d comment=%s",
        db_user.id, product_id, init.payment_comment,
    )


@router.callback_query(F.data.startswith("shop:check:"))
async def cb_check_payment(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    """
    Check TON payment on-chain.
    NEVER marks order as paid on button press alone — blockchain verification required.
    """
    payment_comment = callback.data.removeprefix("shop:check:")
    await callback.answer("🔍 Проверяю транзакцию на блокчейне...", show_alert=False)

    result = await ShopService(session).check_and_pay(payment_comment)
    await session.commit()

    rt = RichTextBuilder()
    if result.paid:
        rt.bold("✅ Оплата подтверждена!\n\n")
        rt.text("Твой заказ передан администратору для выдачи.\n")
        rt.text("Мы уведомим тебя, когда заказ будет готов.")
        t, e = rt.build()
        await callback.message.edit_text(text=t, entities=e, reply_markup=my_orders_kb())
    else:
        rt.bold("⏳ Транзакция не найдена\n\n")
        rt.text(f"{result.reason}\n\n")
        rt.text("Если перевёл — подожди 1–2 минуты и попробуй снова.")
        t, e = rt.build()
        await callback.message.edit_text(
            text=t, entities=e, reply_markup=order_payment_kb(payment_comment)
        )


@router.callback_query(F.data == "shop:my_orders")
async def cb_my_orders(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    await callback.answer()
    from database.repositories.shop_repo import ShopOrderRepository
    orders = await ShopOrderRepository(session).get_orders_for_user(db_user.id)

    rt = RichTextBuilder()
    rt.bold("📋 Мои заказы\n\n")

    if not orders:
        rt.text("Заказов пока нет.")
        t, e = rt.build()
        await callback.message.edit_text(text=t, entities=e, reply_markup=my_orders_kb())
        return

    for order in orders:
        label = _STATUS_LABELS.get(order.status.value, order.status.value)
        rt.bold(f"#{order.id} ")
        rt.text(f"{order.product.title if order.product else '?'} — {label}\n")

    t, e = rt.build()
    await callback.message.edit_text(text=t, entities=e, reply_markup=my_orders_kb())
