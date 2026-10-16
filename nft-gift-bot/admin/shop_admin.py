"""
Shop admin commands.

/shop list                      — list all products
/shop add <title>               — create product (status=DRAFT, not visible)
/shop verify <id> <note>        — REQUIRED: confirm lawful origin, activates product
/shop disable <id>              — take product off sale (INACTIVE)
/shop enable <id>               — re-publish verified product
/shop stock <id> <n>            — set stock count
/shop price <id> <ton>          — update price
/shop delete <id>               — soft-delete product
/shop orders                    — list PAID orders awaiting delivery
/shop deliver <order_id>        — mark order as delivered (admin confirms)
"""
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import AdminFilter
from services.shop_service import ShopService

logger = logging.getLogger(__name__)

shop_admin_router = Router(name="shop_admin")
shop_admin_router.message.filter(AdminFilter())


@shop_admin_router.message(Command("shop"))
async def cmd_shop(message: Message, command: CommandObject, session: AsyncSession) -> None:
    args = (command.args or "").split(maxsplit=2)
    if not args:
        await _show_help(message)
        return

    subcmd = args[0].lower()
    service = ShopService(session)

    # ── list ─────────────────────────────────────────────────────────────────
    if subcmd == "list":
        products = await service.admin_get_all_products()
        if not products:
            await message.answer("Товаров нет.")
            return
        lines = ["<b>Товары магазина</b>\n"]
        for p in products:
            verified = "✅" if p.is_verified else "⚠️"
            lines.append(
                f"#{p.id} {verified} <b>{p.title}</b> "
                f"| {p.status.value} | {p.stock} шт. | {float(p.price_ton):.2f} TON"
            )
        await message.answer("\n".join(lines), parse_mode="HTML")

    # ── add <title> ──────────────────────────────────────────────────────────
    elif subcmd == "add":
        if len(args) < 2:
            await message.answer("Использование: /shop add <название>")
            return
        title = args[1] if len(args) == 2 else " ".join(args[1:])
        price = await service._get_price()
        from database.repositories.shop_repo import ShopProductRepository
        repo = ShopProductRepository(session)
        product = await repo.create(
            title=title,
            description="",
            price_ton=price,
            stock=1,
            delivery_type="manual",
            created_by_admin_id=message.from_user.id,
        )
        await session.commit()
        await message.answer(
            f"✅ Товар #{product.id} создан (статус: DRAFT).\n"
            f"Для публикации выполни: /shop verify {product.id} &lt;описание происхождения&gt;",
            parse_mode="HTML",
        )

    # ── verify <id> <note> ────────────────────────────────────────────────────
    elif subcmd == "verify":
        if len(args) < 3:
            await message.answer(
                "Использование: /shop verify &lt;id&gt; &lt;подтверждение законного владения и способа передачи&gt;",
                parse_mode="HTML",
            )
            return
        try:
            product_id = int(args[1])
        except ValueError:
            await message.answer("ID должен быть числом.")
            return
        note = args[2]
        ok, msg = await service.admin_verify_product(product_id, message.from_user.id, note)
        await session.commit()
        await message.answer(f"{'✅' if ok else '❌'} {msg}")
        if ok:
            logger.info(
                "Admin %d verified product %d: %r", message.from_user.id, product_id, note
            )

    # ── disable <id> ──────────────────────────────────────────────────────────
    elif subcmd == "disable":
        if len(args) < 2:
            await message.answer("Использование: /shop disable <id>")
            return
        try:
            product_id = int(args[1])
        except ValueError:
            await message.answer("ID должен быть числом.")
            return
        ok, msg = await service.admin_disable_product(product_id)
        await session.commit()
        await message.answer(f"{'✅' if ok else '❌'} {msg}")

    # ── enable <id> ───────────────────────────────────────────────────────────
    elif subcmd == "enable":
        if len(args) < 2:
            await message.answer("Использование: /shop enable <id>")
            return
        try:
            product_id = int(args[1])
        except ValueError:
            await message.answer("ID должен быть числом.")
            return
        ok, msg = await service.admin_enable_product(product_id)
        await session.commit()
        await message.answer(f"{'✅' if ok else '❌'} {msg}")

    # ── stock <id> <n> ────────────────────────────────────────────────────────
    elif subcmd == "stock":
        if len(args) < 3:
            await message.answer("Использование: /shop stock <id> <количество>")
            return
        try:
            product_id = int(args[1])
            stock = int(args[2])
        except ValueError:
            await message.answer("ID и количество должны быть числами.")
            return
        if stock < 0:
            await message.answer("Количество не может быть отрицательным.")
            return
        ok, msg = await service.admin_set_stock(product_id, stock)
        await session.commit()
        await message.answer(f"{'✅' if ok else '❌'} {msg}")

    # ── price <id> <ton> ──────────────────────────────────────────────────────
    elif subcmd == "price":
        if len(args) < 3:
            await message.answer("Использование: /shop price <id> <цена_в_TON>")
            return
        try:
            product_id = int(args[1])
            price = float(args[2])
        except ValueError:
            await message.answer("ID должен быть числом, цена — числом (например 5.0).")
            return
        if price <= 0:
            await message.answer("Цена должна быть > 0.")
            return
        product = await service.get_product(product_id)
        if not product:
            await message.answer("Товар не найден.")
            return
        product.price_ton = price
        await session.commit()
        await message.answer(f"✅ Цена товара #{product_id} установлена: {price:.2f} TON")

    # ── delete <id> ───────────────────────────────────────────────────────────
    elif subcmd == "delete":
        if len(args) < 2:
            await message.answer("Использование: /shop delete <id>")
            return
        try:
            product_id = int(args[1])
        except ValueError:
            await message.answer("ID должен быть числом.")
            return
        ok, msg = await service.admin_delete_product(product_id)
        await session.commit()
        await message.answer(f"{'✅' if ok else '❌'} {msg}")

    # ── orders ─────────────────────────────────────────────────────────────────
    elif subcmd == "orders":
        orders = await service.admin_get_paid_orders()
        if not orders:
            await message.answer("Нет оплаченных заказов, ожидающих выдачи.")
            return
        lines = ["<b>Оплаченные заказы (ожидают выдачи)</b>\n"]
        for o in orders:
            paid_str = o.paid_at.strftime("%d.%m %H:%M") if o.paid_at else "?"
            lines.append(
                f"Заказ #{o.id} | user:{o.user_id} | "
                f"{o.product.title if o.product else '?'} | {paid_str}"
            )
        lines.append("\nВыдать: /shop deliver &lt;order_id&gt;")
        await message.answer("\n".join(lines), parse_mode="HTML")

    # ── deliver <order_id> ─────────────────────────────────────────────────────
    elif subcmd == "deliver":
        if len(args) < 2:
            await message.answer("Использование: /shop deliver <order_id>")
            return
        try:
            order_id = int(args[1])
        except ValueError:
            await message.answer("ID заказа должен быть числом.")
            return
        result = await service.deliver_order(order_id, message.from_user.id)
        await session.commit()
        if not result.success:
            await message.answer(f"❌ {result.reason}")
            return
        await message.answer(f"✅ Заказ #{order_id} выдан.")
        if result.delivery_payload:
            # Send encrypted payload privately to admin only — never to the buyer directly
            await message.answer(
                f"<b>Данные для передачи покупателю (защищённый токен):</b>\n"
                f"<code>{result.delivery_payload}</code>\n\n"
                "⚠️ Передай эти данные покупателю по защищённому каналу.",
                parse_mode="HTML",
            )
        logger.info("Admin %d delivered order %d", message.from_user.id, order_id)

    else:
        await _show_help(message)


async def _show_help(message: Message) -> None:
    await message.answer(
        "<b>Команды магазина</b>\n\n"
        "/shop list — список товаров\n"
        "/shop add &lt;название&gt; — добавить товар (статус DRAFT)\n"
        "/shop verify &lt;id&gt; &lt;примечание&gt; — верифицировать и опубликовать\n"
        "/shop disable &lt;id&gt; — снять с продажи\n"
        "/shop enable &lt;id&gt; — опубликовать снова\n"
        "/shop stock &lt;id&gt; &lt;n&gt; — установить остаток\n"
        "/shop price &lt;id&gt; &lt;ton&gt; — изменить цену\n"
        "/shop delete &lt;id&gt; — удалить\n"
        "/shop orders — оплаченные заказы\n"
        "/shop deliver &lt;order_id&gt; — выдать заказ\n\n"
        "⚠️ Товар появляется в каталоге ТОЛЬКО после /shop verify.\n"
        "Верификация подтверждает законное владение и разрешённый способ передачи.",
        parse_mode="HTML",
    )
