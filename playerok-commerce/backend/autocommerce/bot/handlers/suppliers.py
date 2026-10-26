"""🏪 Поставщики: statuses, checks, sync, purchase modes, limits, catalogue,
compliance approval and creating products from supplier positions."""

from __future__ import annotations

from decimal import Decimal

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.enums import COMPLIANCE_LABELS, PURCHASE_MODE_LABELS, SUPPLIER_STATUS_LABELS, ComplianceStatus, PurchaseMode
from ...database.models import Supplier, SupplierProduct
from ...integrations.suppliers import registry
from ...services import catalog, repricing, suppliers
from ...services.audit import Actor, audit
from ...shared.errors import DomainError, NotFound
from ...shared.timeutil import fmt_dt
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, confirm, empty, esc, kb, money, nav, pager, short
from .products import card as product_card

router = make_router("suppliers")


@router.callback_query(F.data == "sup:list")
async def supplier_list(cb: CallbackQuery, session: AsyncSession) -> None:
    rows = (await session.execute(select(Supplier).order_by(Supplier.id))).scalars().all()
    lines = ["🏪 <b>Поставщики</b>", "<i>Статусы — по фактической проверке подключения.</i>", SEP]
    for s in rows:
        lines.append(f"{SUPPLIER_STATUS_LABELS[s.status]} <b>{esc(s.name)}</b> · {PURCHASE_MODE_LABELS[s.purchase_mode]}")
    buttons = [[b(f"{SUPPLIER_STATUS_LABELS[s.status].split()[0]} {s.name}", f"sup:open:{s.id}")] for s in rows]
    await show(cb, "\n".join(lines), kb(*buttons, [b("🔎 Позиции без товара", "res:opp:1")], nav()))


async def supplier_card(session: AsyncSession, supplier_id: int) -> tuple[str, object]:
    s = await suppliers.get_supplier(session, supplier_id)
    cls = registry.adapter_class(s.adapter)
    spent, ops = await suppliers.spent_today(session, s.id)
    count = (await session.execute(select(func.count()).where(SupplierProduct.supplier_id == s.id))).scalar_one()
    caps = cls.capabilities
    lines = [
        f"🏪 <b>{esc(s.name)}</b>",
        f"{esc(s.website or 'без сайта')}",
        SEP,
        f"Статус: <b>{SUPPLIER_STATUS_LABELS[s.status]}</b>",
        f"<i>{esc(short(s.status_reason, 300))}</i>" if s.status_reason else "",
        f"Интеграция: {esc(cls.title)} — {esc(s.integration_method)}",
        f"Возможности API: цены {'✅' if caps.price_list else '—'} · баланс {'✅' if caps.balance else '—'} · закупка {'✅' if caps.purchase else '—'} · коды {'✅' if caps.returns_codes else '—'}",
        f"Режим закупки: <b>{PURCHASE_MODE_LABELS[s.purchase_mode]}</b>",
        f"Баланс: {money(s.balance) if s.balance is not None else '—'} {esc(s.balance_currency or '')} ({fmt_dt(s.balance_checked_at)})",
        f"Лимиты: одна закупка {money(s.max_single_purchase) if s.max_single_purchase else 'нет'} · в сутки {money(s.daily_limit) if s.daily_limit else 'нет'} · операций {s.max_operations_per_day}",
        f"Сегодня: {money(spent)} · операций {ops}",
        f"Позиций в каталоге: {count}",
        f"Операций: успешно {s.success_count} · ошибок {s.error_count}",
        f"Проверка: {fmt_dt(s.last_check_at)} · синхронизация: {fmt_dt(s.last_sync_at)}",
    ]
    if s.last_error:
        lines.append(f"⚠️ {esc(short(s.last_error, 200))}")
    if s.policy_note:
        lines.append(f"🛡 {esc(s.policy_note)}")
    if s.refund_policy:
        lines.append(f"↩️ {esc(s.refund_policy)}")
    ver = s.verification or {}
    if ver.get("facts"):
        lines.append(f"\n🔍 <b>Проверено {esc(ver.get('checked_at', ''))}</b>")
        lines += [f"• {esc(f)}" for f in ver["facts"][:5]]
    rows = [
        [b("🔌 Проверить подключение", f"sup:check:{s.id}", style="primary"), b("🔄 Синхронизировать", f"sup:sync:{s.id}")],
        [b("⚙️ Режим закупки", f"sup:mode:{s.id}"), b("💳 Лимиты", f"sup:limits:{s.id}")],
        [b("📋 Позиции", f"sup:items:{s.id}:1"), b("🔑 Ключи доступа", f"sup:keys:{s.id}")],
        nav("sup:list"),
    ]
    return "\n".join(x for x in lines if x), kb(*rows)


@router.callback_query(F.data.startswith("sup:open:"))
async def open_supplier(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await supplier_card(session, int(cb.data.split(":")[2]))
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("sup:check:"))
async def check(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "suppliers.manage")
    s = await suppliers.get_supplier(session, int(cb.data.split(":")[2]))
    result = await suppliers.check_connection(session, s, actor)
    await cb.answer(("✅ " if result.ok else "⚠️ ") + result.message[:180], show_alert=True)
    text, markup = await supplier_card(session, s.id)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("sup:sync:"))
async def sync(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "suppliers.manage")
    s = await suppliers.get_supplier(session, int(cb.data.split(":")[2]))
    run = await suppliers.sync_catalog(session, s, force=True)
    await cb.answer((run.message if run else "Синхронизация недоступна")[:190], show_alert=True)
    text, markup = await supplier_card(session, s.id)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("sup:keys:"))
async def keys(cb: CallbackQuery, session: AsyncSession) -> None:
    s = await suppliers.get_supplier(session, int(cb.data.split(":")[2]))
    cls = registry.adapter_class(s.adapter)
    from ...services import credentials

    described = await credentials.describe(session, s.code, cls.credential_fields)
    lines = [f"🔑 <b>Ключи: {esc(s.name)}</b>", SEP]
    if not described:
        lines.append(empty("Ключи не требуются"))
    for f in described:
        lines.append(f"{f['label']}: {'✅ ' + esc(f['preview']) if f['source'] else '— не задан'}")
    lines.append("\n🔒 Ключи вводятся только в веб-панели или переменных окружения: секреты не передаются через Telegram.")
    await show(cb, "\n".join(lines), kb(nav(f"sup:open:{s.id}")))


@router.callback_query(F.data.regexp(r"^sup:mode:\d+$"))
async def mode_menu(cb: CallbackQuery, session: AsyncSession) -> None:
    s = await suppliers.get_supplier(session, int(cb.data.split(":")[2]))
    caps = registry.adapter_class(s.adapter).capabilities
    rows = []
    for mode in PurchaseMode:
        available = caps.purchase or mode in (PurchaseMode.MONITOR, PurchaseMode.MANUAL)
        label = ("• " if s.purchase_mode is mode else "") + PURCHASE_MODE_LABELS[mode] + ("" if available else " (нет API)")
        rows.append([b(label, f"sup:setmode:{s.id}:{mode.value}" if available else "noop")])
    text = (
        f"⚙️ <b>Режим закупки: {esc(s.name)}</b>\n{SEP}\n"
        "1. Только мониторинг цен\n2. Ручная закупка через панель\n3. Автоматически после вашего подтверждения\n4. Полностью автоматически — только для разрешённых товаров, в пределах лимитов и дневного бюджета"
    )
    await show(cb, text, kb(*rows, nav(f"sup:open:{s.id}")))


@router.callback_query(F.data.startswith("sup:setmode:"))
async def set_mode(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "suppliers.manage")
    parts = cb.data.split(":")
    sid, mode = int(parts[2]), PurchaseMode(parts[3])
    if mode is PurchaseMode.AUTO and not cb.data.endswith(":y"):
        text, markup = confirm(
            "Включить полностью автоматическую закупку? Деньги будут списываться без вашего подтверждения — в пределах лимитов, бюджета и только для товаров с разрешённой автозакупкой.",
            f"sup:setmode:{sid}:{mode.value}:y",
            f"sup:mode:{sid}",
            danger=True,
        )
        await show(cb, text, markup)
        return
    s = await suppliers.get_supplier(session, sid)
    await suppliers.set_mode(session, s, {"purchase_mode": mode.value}, actor)
    text, markup = await supplier_card(session, sid)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("sup:limits:"))
async def limits(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "suppliers.manage")
    sid = int(cb.data.split(":")[2])
    await ask(
        cb,
        state,
        "sup_limits",
        "Лимиты через пробел: <b>одна_закупка суточный операций_в_сутки</b> (₽, ₽, шт). 0 — без лимита.\nНапример: <code>3000 20000 30</code>",
        back=f"sup:open:{sid}",
        supplier_id=sid,
    )


@on_input("sup_limits")
async def limits_input(message: Message, ctx: dict) -> None:
    parts = message.text.replace(",", ".").split()
    if len(parts) != 3:
        raise DomainError("Нужно три числа")
    try:
        single, daily, ops = Decimal(parts[0]), Decimal(parts[1]), int(parts[2])
    except Exception as exc:
        raise DomainError("Проверьте числа") from exc
    s = await suppliers.get_supplier(ctx["session"], ctx["supplier_id"])
    await suppliers.set_mode(
        ctx["session"], s, {"max_single_purchase": single, "daily_limit": daily, "max_operations_per_day": ops}, ctx["actor"]
    )
    await ctx["state"].clear()
    text, markup = await supplier_card(ctx["session"], s.id)
    await message.answer("✅ Лимиты сохранены\n\n" + text, reply_markup=markup)


@router.callback_query(F.data.startswith("sup:items:"))
async def items(cb: CallbackQuery, session: AsyncSession) -> None:
    _, _, sid, page = cb.data.split(":")
    page_n = int(page)
    stmt = select(SupplierProduct).where(SupplierProduct.supplier_id == int(sid))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(SupplierProduct.id).offset((page_n - 1) * 10).limit(10))).unique().scalars().all()
    text = f"📋 <b>Позиции поставщика</b> · {total}\n{SEP}" + ("" if rows else "\n" + empty("Каталог пуст — нажмите «Синхронизировать»"))
    buttons = [
        [
            b(
                f"{'🟢' if sp.available else '⚪️'} {short(sp.name, 30)} · {sp.price.normalize():f} {sp.currency}"
                if sp.price is not None
                else short(sp.name, 40),
                f"sup:item:{sp.id}",
            )
        ]
        for sp in rows
    ]
    await show(cb, text, kb(*buttons, pager(f"sup:items:{sid}", page_n, total, 10), nav(f"sup:open:{sid}")))


async def item_card(session: AsyncSession, sp_id: int) -> tuple[str, object]:
    sp = await session.get(SupplierProduct, sp_id)
    if sp is None:
        raise NotFound("Позиция не найдена")
    from ...database.models import Product

    product = (await session.execute(select(Product).where(Product.preferred_supplier_product_id == sp.id))).unique().scalar_one_or_none()
    lines = [
        f"📋 <b>{esc(sp.name)}</b>",
        f"{esc(sp.supplier.name)} · <code>{esc(sp.external_id)}</code>",
        SEP,
        f"Цена: <b>{sp.price.normalize():f} {sp.currency}</b>" + (f" за {sp.price_unit} шт" if sp.price_unit > 1 else "")
        if sp.price is not None
        else "Цена: —",
        f"Категория поставщика: {esc(sp.category or '—')}",
        f"Количество: {sp.min_quantity or '—'}–{sp.max_quantity or '—'}" if sp.min_quantity or sp.max_quantity else "",
        f"Регион: {esc(sp.region)}" if sp.region else "",
        f"Доступна: {'да' if sp.available else 'нет'}",
        f"Правила платформы: {COMPLIANCE_LABELS[sp.compliance_status]}",
        f"Проверено: {fmt_dt(sp.last_seen_at)} · цена менялась: {fmt_dt(sp.price_changed_at)}",
    ]
    rows = []
    if product:
        lines.append(f"\n📦 Товар: {esc(product.name)}")
        rows.append([b("📦 Открыть товар", f"prd:open:{product.id}")])
    else:
        rows.append([b("➕ Создать товар", f"sup:mk:{sp.id}", style="primary")])
    if sp.compliance_status is not ComplianceStatus.APPROVED:
        rows.append([b("✅ Одобрить (правила проверены)", f"sup:cmp:{sp.id}:approved")])
    else:
        rows.append([b("🛑 Запретить", f"sup:cmp:{sp.id}:blocked")])
    rows.append(nav(f"sup:items:{sp.supplier_id}:1"))
    return "\n".join(x for x in lines if x), kb(*rows)


@router.callback_query(F.data.startswith("sup:item:"))
async def open_item(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await item_card(session, int(cb.data.split(":")[2]))
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("sup:cmp:"))
async def compliance(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "suppliers.manage")
    _, _, sp_id, status = cb.data.split(":")
    sp = await session.get(SupplierProduct, int(sp_id))
    if sp is None:
        raise NotFound("Позиция не найдена")
    sp.compliance_status = ComplianceStatus(status)
    await audit(session, actor, "supplier_product.compliance", entity_type="supplier_product", entity_id=sp.id, details={"status": status})
    text, markup = await item_card(session, sp.id)
    await show(cb, text, markup)


@router.callback_query(F.data.regexp(r"^sup:mk:\d+$"))
async def make_product(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "products.manage")
    sp_id = int(cb.data.split(":")[2])
    sp = await session.get(SupplierProduct, sp_id)
    if sp is None:
        raise NotFound("Позиция не найдена")
    cats = [c for c in await catalog.list_categories(session) if c.code in (sp.supplier.categories or [])] or await catalog.list_categories(
        session
    )
    rows = [[b(short(c.name, 36), f"sup:mk:{sp_id}:{c.code}")] for c in cats]
    await show(cb, f"➕ <b>Товар из позиции</b>\n{esc(sp.name)}\n\nВыберите категорию PlayerOK:", kb(*rows, nav(f"sup:item:{sp_id}")))


@router.callback_query(F.data.regexp(r"^sup:mk:\d+:[a-z_]+$"))
async def make_product_do(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "products.manage")
    _, _, sp_id, code = cb.data.split(":")
    sp = await session.get(SupplierProduct, int(sp_id))
    if sp is None:
        raise NotFound("Позиция не найдена")
    product = await catalog.create_from_supplier_item(session, sp, code, actor)
    await repricing.reprice_product(session, product, actor=actor, notify_owner=False)
    text, markup = await product_card(session, product.id)
    await show(cb, "✅ Товар создан (черновик). Проверьте описание, регион и активируйте.\n\n" + text, markup)
