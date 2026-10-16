"""
Inline admin panel — all section handlers.

All callbacks prefixed with 'adm:' are handled here.
The router enforces AdminFilter on both messages and callbacks.
"""
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.keyboards import (
    admins_kb,
    back_panel_kb,
    cancel_kb,
    confirm_kb,
    main_panel_kb,
    orders_list_kb,
    product_actions_kb,
    settings_kb,
    shop_list_kb,
)
from admin.states import AdminFSM
from bot.filters.admin import AdminFilter
from bot.ui.rich_text import RichTextBuilder
from config import settings
from database.models.user import User
from database.repositories.audit_repo import AuditRepository
from database.repositories.bot_setting_repo import BotSettingRepository
from database.repositories.shop_repo import ShopOrderRepository, ShopProductRepository
from database.repositories.user_repo import UserRepository
from payments.payment_service import (
    SETTING_SUB_DURATION_DAYS,
    SETTING_SUB_PRICE_TON,
    DEFAULT_SUB_DURATION_DAYS,
    DEFAULT_SUB_PRICE_TON,
    PaymentService,
)
from services.admin_stats import AdminStatsService
from services.shop_service import (
    SETTING_SHOP_PRICE_TON,
    DEFAULT_SHOP_PRICE_TON,
    ShopService,
)

logger = logging.getLogger(__name__)

panel_router = Router(name="admin_panel")
panel_router.message.filter(AdminFilter())
panel_router.callback_query.filter(AdminFilter())

_NANOTON = 1_000_000_000


# ── Helpers ────────────────────────────────────────────────────────────────


async def _safe_edit(callback: CallbackQuery, text: str, entities, markup) -> None:
    try:
        await callback.message.edit_text(text=text, entities=entities, reply_markup=markup)
    except TelegramBadRequest:
        pass


def _build_main_panel() -> tuple[str, list]:
    rt = RichTextBuilder()
    rt.bold("🛠 Панель администратора\n\n")
    rt.text("Выберите раздел:")
    return rt.build()


async def _get_settings_values(session: AsyncSession) -> tuple[int, float, float]:
    repo = BotSettingRepository(session)
    raw_dur = await repo.get(SETTING_SUB_DURATION_DAYS)
    sub_dur = int(raw_dur) if raw_dur and raw_dur.isdigit() else DEFAULT_SUB_DURATION_DAYS
    raw_sp = await repo.get(SETTING_SUB_PRICE_TON)
    try:
        sub_price = float(raw_sp) if raw_sp else DEFAULT_SUB_PRICE_TON
    except ValueError:
        sub_price = DEFAULT_SUB_PRICE_TON
    raw_shp = await repo.get(SETTING_SHOP_PRICE_TON)
    try:
        shop_price = float(raw_shp) if raw_shp else DEFAULT_SHOP_PRICE_TON
    except ValueError:
        shop_price = DEFAULT_SHOP_PRICE_TON
    return sub_dur, sub_price, shop_price


# ── Entry: /admin command ──────────────────────────────────────────────────


@panel_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    t, e = _build_main_panel()
    await message.answer(text=t, entities=e, reply_markup=main_panel_kb())


# ── Main panel navigation ─────────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:home")
async def cb_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    t, e = _build_main_panel()
    await _safe_edit(callback, t, e, main_panel_kb())


# ── Statistics ────────────────────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    s = await AdminStatsService(session).get_stats()

    rt = RichTextBuilder()
    rt.bold("📊 Статистика\n\n")
    rt.bold("Пользователи: "); rt.text(f"{s.total_users}\n")
    rt.bold("Активные подписки: "); rt.text(f"{s.active_subs_total}")
    rt.text(f" (Basic: {s.active_subs_basic}, Premium: {s.active_subs_premium})\n\n")
    rt.bold("Платежи (30 дн.):\n")
    rt.text(f"  Ожидают: {s.pending_payments}\n")
    rt.text(f"  Подтверждено: {s.confirmed_payments_30d}\n")
    rt.text(f"  Выручка: {s.revenue_ton_30d:.4f} TON\n\n")
    rt.bold("Заказы магазина:\n")
    rt.text(f"  Ожидают оплаты: {s.shop_orders_pending}\n")
    rt.text(f"  Оплачены: {s.shop_orders_paid}\n")
    rt.text(f"  Выданы: {s.shop_orders_delivered}\n")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())


# ── Payments list ─────────────────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:payments")
async def cb_payments(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    from database.models.payment import TonPayment
    result = await session.execute(
        select(TonPayment).order_by(TonPayment.created_at.desc()).limit(10)
    )
    payments = list(result.scalars().all())

    rt = RichTextBuilder()
    rt.bold("💳 Последние платежи\n\n")
    if not payments:
        rt.text("Платежей нет.")
    for p in payments:
        amt = f"{p.amount_nanoton / _NANOTON:.2f} TON" if p.amount_nanoton else "?"
        date = p.created_at.strftime("%d.%m %H:%M") if p.created_at else "?"
        rt.text(f"#{p.id} user:{p.user_id} {p.status.value} {amt} {date}\n")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())


# ── Orders list (PAID, awaiting delivery) ────────────────────────────────


@panel_router.callback_query(F.data == "adm:orders")
async def cb_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    orders = await ShopOrderRepository(session).get_pending_orders_admin()

    rt = RichTextBuilder()
    rt.bold("🛒 Заказы, ожидающие выдачи\n\n")
    if not orders:
        rt.text("Нет оплаченных заказов.")
        t, e = rt.build()
        await _safe_edit(callback, t, e, back_panel_kb())
        return

    for o in orders:
        title = o.product.title[:25] if o.product else "?"
        paid_str = o.paid_at.strftime("%d.%m %H:%M") if o.paid_at else "?"
        rt.text(f"#{o.id} {title} | user:{o.user_id} | {paid_str}\n")
    t, e = rt.build()
    await _safe_edit(callback, t, e, orders_list_kb(orders))


# ── Settings ──────────────────────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:settings")
async def cb_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    sub_dur, sub_price, shop_price = await _get_settings_values(session)

    rt = RichTextBuilder()
    rt.bold("⚙️ Настройки\n\n")
    rt.text("Нажмите на параметр, чтобы изменить:")
    t, e = rt.build()
    await _safe_edit(callback, t, e, settings_kb(sub_dur, sub_price, shop_price))


@panel_router.callback_query(F.data == "adm:settings:sub_dur")
async def cb_set_sub_dur(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdminFSM.enter_sub_duration)
    rt = RichTextBuilder()
    rt.bold("⏱ Срок подписки\n\n")
    rt.text("Введите количество дней (целое число > 0):")
    t, e = rt.build()
    await _safe_edit(callback, t, e, cancel_kb())


@panel_router.callback_query(F.data == "adm:settings:sub_price")
async def cb_set_sub_price(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdminFSM.enter_sub_price)
    rt = RichTextBuilder()
    rt.bold("💰 Цена подписки\n\n")
    rt.text("Введите цену в TON (например: 10.0):")
    t, e = rt.build()
    await _safe_edit(callback, t, e, cancel_kb())


@panel_router.callback_query(F.data == "adm:settings:shop_price")
async def cb_set_shop_price(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdminFSM.enter_shop_price)
    rt = RichTextBuilder()
    rt.bold("🏷 Цена товара в магазине\n\n")
    rt.text("Введите цену в TON (например: 5.0):")
    t, e = rt.build()
    await _safe_edit(callback, t, e, cancel_kb())


@panel_router.message(AdminFSM.enter_sub_duration)
async def fsm_sub_duration(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    val = (message.text or "").strip()
    if not val.isdigit() or int(val) < 1:
        await message.answer("❌ Введите целое число > 0")
        return
    days = int(val)
    await PaymentService(session).set_sub_duration(days)
    await AuditRepository(session).log(
        message.from_user.id, "set_sub_duration", f"sub_duration_days={days}"
    )
    await session.commit()
    await state.clear()
    rt = RichTextBuilder()
    rt.bold("✅ Обновлено\n\n")
    rt.text(f"Срок подписки: {days} дней")
    t, e = rt.build()
    sub_dur, sub_price, shop_price = await _get_settings_values(session)
    await message.answer(text=t, entities=e, reply_markup=settings_kb(sub_dur, sub_price, shop_price))


@panel_router.message(AdminFSM.enter_sub_price)
async def fsm_sub_price(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    val = (message.text or "").strip().replace(",", ".")
    try:
        price = float(val)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число > 0, например 10.5")
        return
    await PaymentService(session).set_sub_price(price)
    await AuditRepository(session).log(
        message.from_user.id, "set_sub_price", f"sub_price_ton={price:.4f}"
    )
    await session.commit()
    await state.clear()
    rt = RichTextBuilder()
    rt.bold("✅ Обновлено\n\n")
    rt.text(f"Цена подписки: {price:.2f} TON")
    t, e = rt.build()
    sub_dur, sub_price, shop_price = await _get_settings_values(session)
    await message.answer(text=t, entities=e, reply_markup=settings_kb(sub_dur, sub_price, shop_price))


@panel_router.message(AdminFSM.enter_shop_price)
async def fsm_shop_price(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    val = (message.text or "").strip().replace(",", ".")
    try:
        price = float(val)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число > 0, например 5.0")
        return
    await ShopService(session).set_shop_price(price)
    await AuditRepository(session).log(
        message.from_user.id, "set_shop_price", f"shop_price_ton={price:.4f}"
    )
    await session.commit()
    await state.clear()
    rt = RichTextBuilder()
    rt.bold("✅ Обновлено\n\n")
    rt.text(f"Цена в магазине: {price:.2f} TON")
    t, e = rt.build()
    sub_dur, sub_price, shop_price = await _get_settings_values(session)
    await message.answer(text=t, entities=e, reply_markup=settings_kb(sub_dur, sub_price, shop_price))


# ── Shop products ─────────────────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:shop")
async def cb_shop(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    products = await ShopProductRepository(session).get_all_admin()

    rt = RichTextBuilder()
    rt.bold("🏪 Товары магазина\n\n")
    if not products:
        rt.text("Товаров нет. Добавь через /shop add <название>")
    else:
        rt.text(f"Всего: {len(products)} шт.")
    t, e = rt.build()
    await _safe_edit(callback, t, e, shop_list_kb(products))


@panel_router.callback_query(F.data.startswith("adm:shop:p:"))
async def cb_shop_product(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    product_id = int(callback.data.removeprefix("adm:shop:p:"))
    product = await ShopProductRepository(session).get_by_id(product_id)

    if not product:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    rt = RichTextBuilder()
    rt.bold(f"#{product.id} {product.title}\n\n")
    rt.bold("Статус: "); rt.text(f"{product.status.value}\n")
    rt.bold("Верифицирован: "); rt.text(f"{'Да' if product.is_verified else 'Нет'}\n")
    rt.bold("Цена: "); rt.text(f"{float(product.price_ton):.2f} TON\n")
    rt.bold("Остаток: "); rt.text(f"{product.stock} шт.\n")
    if product.description:
        rt.bold("Описание: "); rt.text(f"{product.description[:200]}\n")
    if product.verification_note:
        rt.bold("Примечание верификации: ")
        rt.text(f"{product.verification_note[:200]}\n")
    t, e = rt.build()
    await _safe_edit(callback, t, e, product_actions_kb(product))


@panel_router.callback_query(F.data.startswith("adm:shop:verify:"))
async def cb_shop_verify(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    product_id = int(callback.data.removeprefix("adm:shop:verify:"))
    await state.set_state(AdminFSM.enter_verify_note)
    await state.update_data(product_id=product_id)

    rt = RichTextBuilder()
    rt.bold("✅ Верификация товара\n\n")
    rt.text("Введите подтверждение законного происхождения и разрешённого способа передачи товара:\n")
    rt.italic("(Это сообщение будет сохранено в журнале аудита)")
    t, e = rt.build()
    await _safe_edit(callback, t, e, cancel_kb())


@panel_router.message(AdminFSM.enter_verify_note)
async def fsm_verify_note(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    note = (message.text or "").strip()
    if len(note) < 10:
        await message.answer("❌ Введите более подробное описание (минимум 10 символов)")
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    if not product_id:
        await state.clear()
        await message.answer("Ошибка: ID товара утерян. Начните заново.")
        return

    ok, msg = await ShopService(session).admin_verify_product(
        product_id, message.from_user.id, note
    )
    if ok:
        await AuditRepository(session).log(
            message.from_user.id,
            "verify_product",
            f"product_id={product_id} note={note[:200]}",
            target_id=product_id,
        )
    await session.commit()
    await state.clear()

    rt = RichTextBuilder()
    rt.bold(f"{'✅' if ok else '❌'} {msg}\n")
    t, e = rt.build()
    await message.answer(text=t, entities=e, reply_markup=back_panel_kb())


@panel_router.callback_query(F.data.startswith("adm:shop:dis:"))
async def cb_shop_disable(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    await callback.answer()
    product_id = int(callback.data.removeprefix("adm:shop:dis:"))
    ok, msg = await ShopService(session).admin_disable_product(product_id)
    if ok:
        await AuditRepository(session).log(
            callback.from_user.id,
            "disable_product",
            f"product_id={product_id}",
            target_id=product_id,
        )
    await session.commit()

    rt = RichTextBuilder()
    rt.bold(f"{'✅' if ok else '❌'} {msg}")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())


@panel_router.callback_query(F.data.startswith("adm:shop:en:"))
async def cb_shop_enable(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    await callback.answer()
    product_id = int(callback.data.removeprefix("adm:shop:en:"))
    ok, msg = await ShopService(session).admin_enable_product(product_id)
    if ok:
        await AuditRepository(session).log(
            callback.from_user.id,
            "enable_product",
            f"product_id={product_id}",
            target_id=product_id,
        )
    await session.commit()

    rt = RichTextBuilder()
    rt.bold(f"{'✅' if ok else '❌'} {msg}")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())


@panel_router.callback_query(F.data.startswith("adm:confirm:del_prod:"))
async def cb_confirm_del_prod(callback: CallbackQuery) -> None:
    await callback.answer()
    product_id = callback.data.removeprefix("adm:confirm:del_prod:")
    rt = RichTextBuilder()
    rt.bold("🗑 Удаление товара\n\n")
    rt.text(f"Удалить товар #{product_id}? Это действие необратимо.")
    t, e = rt.build()
    await _safe_edit(callback, t, e, confirm_kb(f"del_prod:{product_id}"))


@panel_router.callback_query(F.data.startswith("adm:do:del_prod:"))
async def cb_do_del_prod(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    await callback.answer()
    product_id = int(callback.data.removeprefix("adm:do:del_prod:"))
    ok, msg = await ShopService(session).admin_delete_product(product_id)
    if ok:
        await AuditRepository(session).log(
            callback.from_user.id,
            "delete_product",
            f"product_id={product_id}",
            target_id=product_id,
        )
    await session.commit()

    rt = RichTextBuilder()
    rt.bold(f"{'✅' if ok else '❌'} {msg}")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())


# ── Deliver order ─────────────────────────────────────────────────────────


@panel_router.callback_query(F.data.startswith("adm:confirm:deliver:"))
async def cb_confirm_deliver(callback: CallbackQuery) -> None:
    await callback.answer()
    order_id = callback.data.removeprefix("adm:confirm:deliver:")
    rt = RichTextBuilder()
    rt.bold("📦 Выдача заказа\n\n")
    rt.text(f"Подтвердить выдачу заказа #{order_id}?")
    t, e = rt.build()
    await _safe_edit(callback, t, e, confirm_kb(f"deliver:{order_id}"))


@panel_router.callback_query(F.data.startswith("adm:do:deliver:"))
async def cb_do_deliver(
    callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User
) -> None:
    await callback.answer()
    order_id = int(callback.data.removeprefix("adm:do:deliver:"))
    result = await ShopService(session).deliver_order(order_id, callback.from_user.id)

    if result.success:
        await AuditRepository(session).log(
            callback.from_user.id,
            "deliver_order",
            f"order_id={order_id}",
            target_id=order_id,
        )
    await session.commit()

    rt = RichTextBuilder()
    rt.bold(f"{'✅' if result.success else '❌'} {result.reason}")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())

    if result.success and result.delivery_payload:
        # Send payload privately to admin only — never exposed in group or to buyer
        dp_rt = RichTextBuilder()
        dp_rt.bold("🔐 Данные для передачи покупателю:\n\n")
        dp_rt.code(result.delivery_payload)
        dp_rt.text("\n\n⚠️ Передай по защищённому каналу. Не пересылай в группы.")
        dp_t, dp_e = dp_rt.build()
        try:
            await bot.send_message(
                callback.from_user.id,
                text=dp_t,
                entities=dp_e,
            )
        except Exception:
            pass


# ── Audit log ─────────────────────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:audit")
async def cb_audit(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    entries = await AuditRepository(session).get_recent(20)

    rt = RichTextBuilder()
    rt.bold("📋 Журнал аудита (последние 20)\n\n")
    if not entries:
        rt.text("Записей нет.")
    for e_log in entries:
        date = e_log.created_at.strftime("%d.%m %H:%M")
        rt.bold(f"{date} ")
        rt.text(f"admin:{e_log.admin_telegram_id} ")
        rt.bold(f"{e_log.action}\n")
        rt.italic(f"  {e_log.details[:80]}\n")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())


# ── Admins management ─────────────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:admins")
async def cb_admins(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    result = await session.execute(
        select(User).where(User.is_admin.is_(True))
    )
    db_admins = list(result.scalars().all())

    rt = RichTextBuilder()
    rt.bold("👑 Администраторы\n\n")
    rt.bold("Суперадмины (env): ")
    rt.text(", ".join(str(x) for x in settings.bot_admin_ids) + "\n\n")
    rt.bold("DB-администраторы:\n")
    if not db_admins:
        rt.text("Нет\n")
    else:
        for a in db_admins:
            label = f"@{a.username}" if a.username else str(a.telegram_id)
            is_env = a.telegram_id in settings.bot_admin_ids
            rt.text(f"  {label}{'  🔒' if is_env else ''}\n")
    t, e = rt.build()
    await _safe_edit(callback, t, e, admins_kb(db_admins, list(settings.bot_admin_ids)))


@panel_router.callback_query(F.data == "adm:admins:add")
async def cb_admins_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdminFSM.enter_new_admin_id)
    rt = RichTextBuilder()
    rt.bold("➕ Добавить администратора\n\n")
    rt.text("Введите Telegram ID нового администратора.\n")
    rt.text("Пользователь должен уже взаимодействовать с ботом.")
    t, e = rt.build()
    await _safe_edit(callback, t, e, cancel_kb())


@panel_router.message(AdminFSM.enter_new_admin_id)
async def fsm_new_admin(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    val = (message.text or "").strip()
    if not val.lstrip("-").isdigit():
        await message.answer("❌ Введите числовой Telegram ID")
        return
    target_tg_id = int(val)

    if target_tg_id in settings.bot_admin_ids:
        await message.answer("ℹ️ Этот пользователь уже является суперадмином.")
        await state.clear()
        return

    repo = UserRepository(session)
    target_user = await repo.get_by_telegram_id(target_tg_id)
    if not target_user:
        await message.answer(
            "❌ Пользователь не найден в базе. "
            "Он должен сначала написать боту."
        )
        return

    await repo.set_admin(target_tg_id, is_admin=True)
    await AuditRepository(session).log(
        message.from_user.id,
        "add_admin",
        f"added telegram_id={target_tg_id} (@{target_user.username or '?'})",
        target_id=target_user.id,
    )
    await session.commit()
    await state.clear()

    rt = RichTextBuilder()
    rt.bold("✅ Администратор добавлен\n\n")
    label = f"@{target_user.username}" if target_user.username else str(target_tg_id)
    rt.text(f"{label} теперь администратор.")
    t, e = rt.build()
    await message.answer(text=t, entities=e, reply_markup=back_panel_kb())


@panel_router.callback_query(F.data.startswith("adm:confirm:rm_admin:"))
async def cb_confirm_rm_admin(callback: CallbackQuery) -> None:
    await callback.answer()
    tg_id = callback.data.removeprefix("adm:confirm:rm_admin:")

    if int(tg_id) in settings.bot_admin_ids:
        await callback.answer(
            "Нельзя удалить суперадмина из ENV.", show_alert=True
        )
        return

    rt = RichTextBuilder()
    rt.bold("👑 Удаление администратора\n\n")
    rt.text(f"Лишить прав администратора пользователя {tg_id}?")
    t, e = rt.build()
    await _safe_edit(callback, t, e, confirm_kb(f"rm_admin:{tg_id}"))


@panel_router.callback_query(F.data.startswith("adm:do:rm_admin:"))
async def cb_do_rm_admin(
    callback: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    await callback.answer()
    tg_id = int(callback.data.removeprefix("adm:do:rm_admin:"))

    if tg_id in settings.bot_admin_ids:
        await callback.answer(
            "Нельзя удалить суперадмина из ENV.", show_alert=True
        )
        return

    repo = UserRepository(session)
    target = await repo.get_by_telegram_id(tg_id)
    if target:
        await repo.set_admin(tg_id, is_admin=False)
        await AuditRepository(session).log(
            callback.from_user.id,
            "remove_admin",
            f"removed telegram_id={tg_id} (@{target.username or '?'})",
            target_id=target.id,
        )
    await session.commit()

    rt = RichTextBuilder()
    rt.bold("✅ Права администратора отозваны.")
    t, e = rt.build()
    await _safe_edit(callback, t, e, back_panel_kb())


# ── Cancel FSM from callback ──────────────────────────────────────────────


@panel_router.callback_query(F.data == "adm:cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    t, e = _build_main_panel()
    await _safe_edit(callback, t, e, main_panel_kb())
