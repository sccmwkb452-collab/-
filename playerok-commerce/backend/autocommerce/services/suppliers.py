"""Suppliers: connection checks, catalogue and price sync, purchasing.

Purchase safety:

* one supplier order per order item and attempt, keyed by an idempotency key
  (UNIQUE): repeated processing returns the existing purchase;
* the intent row is committed *before* the API call; a crash between the call
  and the commit leaves a CREATED row that is treated as UNKNOWN on restart —
  never re-sent automatically;
* guards: kill switch, purchase mode, compliance, freshness of the price,
  single and daily limits, operations per day, global daily budget for
  automatic purchases, supplier balance, profit of the sold order;
* test mode simulates the purchase (no API call) and marks everything as test.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import (
    ComplianceStatus,
    DeliveryType,
    PurchaseMode,
    Severity,
    SupplierOrderStatus,
    SupplierStatus,
    SyncStatus,
)
from ..database.models import Order, OrderItem, Product, Supplier, SupplierOrder, SupplierPriceHistory, SupplierProduct, SyncRun
from ..database.session import session_scope
from ..integrations.http import IntegrationError
from ..integrations.suppliers import registry
from ..integrations.suppliers.base import ConnectionCheck, PurchaseNotSupported, PurchaseRequest, PurchaseResult, SupplierAdapter
from ..shared.errors import Blocked, Conflict, NotFound
from ..shared.masking import scrub, scrub_text
from ..shared.money import fmt_money, money
from ..shared.timeutil import local_day_bounds, local_today, utcnow
from . import app_settings, credentials, fx, jobs, sync
from .audit import SYSTEM, Actor, audit
from .catalog import compliance_of
from .notifications import btn, esc, notify

UNKNOWN_AFTER = timedelta(minutes=10)  # CREATED rows older than this are treated as UNKNOWN


class ManualPurchaseRequired(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class ConfirmationRequired(Exception):
    def __init__(self, reason: str, cost_rub: Decimal | None):
        super().__init__(reason)
        self.reason = reason
        self.cost_rub = cost_rub


async def get_supplier(session: AsyncSession, ref: int | str) -> Supplier:
    query = select(Supplier).where(Supplier.id == ref if isinstance(ref, int) else Supplier.code == ref)
    supplier = (await session.execute(query)).scalar_one_or_none()
    if supplier is None:
        raise NotFound("Поставщик не найден")
    return supplier


def adapter_options(supplier: Supplier) -> dict[str, Any]:
    settings = get_settings()
    return {"sandbox": settings.reloadly_sandbox, "currency": supplier.currency, "api_url": settings.vexboost_api_url}


async def build_adapter(session: AsyncSession, supplier: Supplier) -> SupplierAdapter:
    cls = registry.adapter_class(supplier.adapter)
    creds = await credentials.get_credentials(session, supplier.code, cls.credential_fields)
    return registry.build(supplier.code, supplier.adapter, creds, adapter_options(supplier))


async def check_connection(session: AsyncSession, supplier: Supplier, actor: Actor = SYSTEM) -> ConnectionCheck:
    run = await sync.start(session, f"supplier:{supplier.code}", "check")
    supplier.last_check_at = utcnow()
    if supplier.status in (SupplierStatus.BLOCKED_BY_POLICY, SupplierStatus.DISABLED):
        sync.finish(run, SyncStatus.UNAVAILABLE, message=supplier.status_reason)
        return ConnectionCheck(False, supplier.status_reason or "Поставщик отключён")
    adapter = await build_adapter(session, supplier)
    if not adapter.configured():
        supplier.status = SupplierStatus.NOT_CONFIGURED
        result = ConnectionCheck(False, "Не заданы ключи доступа")
        sync.finish(run, SyncStatus.UNAVAILABLE, message=result.message)
        return result
    try:
        result = await adapter.check()
    except Exception as exc:  # noqa: BLE001 - any adapter failure is a failed check
        result = ConnectionCheck(False, scrub_text(f"{type(exc).__name__}: {exc}"))
    if result.ok:
        supplier.status = SupplierStatus.MONITOR_ONLY if not adapter.capabilities.purchase else SupplierStatus.CONNECTED
        supplier.last_error = None
        if result.balance is not None:
            supplier.balance = money(result.balance)
            supplier.balance_currency = result.currency
            supplier.balance_checked_at = utcnow()
    else:
        supplier.status = SupplierStatus.ERROR
        supplier.last_error = result.message[:2000]
        supplier.error_count += 1
    supplier.status_reason = result.message[:2000]
    sync.finish(run, SyncStatus.SUCCEEDED if result.ok else SyncStatus.FAILED, errors=0 if result.ok else 1, message=result.message)
    await audit(session, actor, "supplier.check", entity_type="supplier", entity_id=supplier.id, details={"ok": result.ok})
    return result


async def sync_catalog(session: AsyncSession, supplier: Supplier, *, force: bool = False) -> SyncRun | None:
    settings = get_settings()
    if supplier.status in (SupplierStatus.BLOCKED_BY_POLICY, SupplierStatus.DISABLED):
        return None
    if (
        supplier.adapter == "fragment"
        and not force
        and supplier.last_sync_at
        and utcnow() - supplier.last_sync_at < timedelta(minutes=settings.fragment_min_interval_minutes)
    ):
        return None  # public pages: no more often than the configured interval
    adapter = await build_adapter(session, supplier)
    run = await sync.start(session, f"supplier:{supplier.code}", "catalog")
    if not adapter.capabilities.price_list:
        return sync.finish(run, SyncStatus.UNAVAILABLE, message="У поставщика нет API цен — цены вносятся вручную")
    if not adapter.configured():
        return sync.finish(run, SyncStatus.UNAVAILABLE, message="Не заданы ключи доступа")
    try:
        items = await adapter.fetch_catalog()
    except (IntegrationError, Exception) as exc:  # noqa: BLE001
        supplier.status = SupplierStatus.ERROR
        supplier.last_error = scrub_text(str(exc))[:2000]
        supplier.error_count += 1
        await notify(
            session,
            "supplier_error",
            f"Поставщик {supplier.name}: ошибка синхронизации",
            esc(supplier.last_error),
            severity=Severity.WARNING,
            buttons=[[btn("🏪 Открыть поставщика", f"sup:open:{supplier.id}")]],
            entity_type="supplier",
            entity_id=supplier.id,
            dedupe_key=f"supplier_sync_error:{supplier.id}:{local_today().isoformat()}",
        )
        return sync.finish(run, SyncStatus.FAILED, errors=1, message=supplier.last_error)

    existing = {
        sp.external_id: sp
        for sp in (await session.execute(select(SupplierProduct).where(SupplierProduct.supplier_id == supplier.id))).scalars()
    }
    now = utcnow()
    saved, changed_ids, errors = 0, [], 0
    default_compliance = ComplianceStatus.NEEDS_REVIEW
    if supplier.adapter == "fragment":
        default_compliance = ComplianceStatus.APPROVED  # Stars/Premium gifting is a platform feature
    seen: set[str] = set()
    for item in items:
        seen.add(item.external_id)
        sp = existing.get(item.external_id)
        price_rub = await fx.to_rub(session, item.price, item.currency) if item.price is not None else None
        if sp is None:
            sp = SupplierProduct(
                supplier_id=supplier.id,
                external_id=item.external_id,
                name=item.name,
                compliance_status=default_compliance,
            )
            session.add(sp)
            changed = True
        else:
            changed = sp.price != item.price or sp.currency != item.currency
        sp.name = item.name[:300]
        sp.category = item.category[:120]
        sp.price = item.price
        sp.price_unit = item.price_unit
        sp.currency = item.currency
        sp.min_quantity = item.min_quantity
        sp.max_quantity = item.max_quantity
        sp.region = item.region[:64]
        sp.available = item.available
        sp.raw = scrub(item.raw)
        sp.last_seen_at = now
        if changed and item.price is not None:
            sp.price_changed_at = now
            await session.flush()
            session.add(
                SupplierPriceHistory(
                    supplier_product_id=sp.id, price=item.price, currency=item.currency, price_rub=price_rub, captured_at=now
                )
            )
            changed_ids.append(sp.id)
        saved += 1
    for ext_id, sp in existing.items():
        if ext_id not in seen and sp.available:
            sp.available = False
            changed_ids.append(sp.id)
    supplier.last_sync_at = now
    if supplier.status in (SupplierStatus.ERROR, SupplierStatus.NOT_CONFIGURED):
        supplier.status = SupplierStatus.MONITOR_ONLY if not adapter.capabilities.purchase else SupplierStatus.CONNECTED
        supplier.last_error = None
    await session.flush()
    # products linked to changed positions are repriced by the worker
    if changed_ids:
        linked = (await session.execute(select(Product.id).where(Product.preferred_supplier_product_id.in_(changed_ids)))).scalars().all()
        for pid in linked:
            await jobs.enqueue(session, "product.reprice", {"product_id": pid}, dedupe_key=f"reprice:{pid}")
    return sync.finish(
        run,
        SyncStatus.SUCCEEDED if not errors else SyncStatus.PARTIAL,
        received=len(items),
        saved=saved,
        errors=errors,
        message=f"Получено позиций: {len(items)}, изменений цен: {len(changed_ids)}",
        details={"changed": len(changed_ids)},
    )


async def set_mode(session: AsyncSession, supplier: Supplier, data: dict[str, Any], actor: Actor) -> Supplier:
    if "purchase_mode" in data:
        mode = PurchaseMode(data["purchase_mode"])
        if supplier.status is SupplierStatus.BLOCKED_BY_POLICY and mode is not PurchaseMode.MONITOR:
            raise Blocked("Поставщик заблокирован политикой")
        adapter_cls = registry.adapter_class(supplier.adapter)
        if mode in (PurchaseMode.CONFIRM, PurchaseMode.AUTO) and not adapter_cls.capabilities.purchase:
            raise Blocked("У поставщика нет API закупки: доступны только мониторинг и ручная закупка")
        supplier.purchase_mode = mode
    for key in ("max_single_purchase", "daily_limit", "fee_fixed"):
        if key in data and data[key] not in (None, ""):
            setattr(supplier, key, money(data[key]))
    if "fee_pct" in data and data["fee_pct"] not in (None, ""):
        supplier.fee_pct = Decimal(str(data["fee_pct"]))
    if "max_operations_per_day" in data:
        supplier.max_operations_per_day = max(0, int(data["max_operations_per_day"]))
    if "enabled" in data and supplier.status is not SupplierStatus.BLOCKED_BY_POLICY:
        supplier.status = SupplierStatus.NOT_CONFIGURED if data["enabled"] else SupplierStatus.DISABLED
    if supplier.purchase_mode is PurchaseMode.AUTO and (supplier.max_single_purchase <= 0 or supplier.daily_limit <= 0):
        raise Blocked("Для полностью автоматической закупки задайте лимит одной закупки и суточный лимит")
    await audit(
        session, actor, "supplier.update", entity_type="supplier", entity_id=supplier.id, details={k: str(v) for k, v in data.items()}
    )
    return supplier


async def spent_today(session: AsyncSession, supplier_id: int | None = None) -> tuple[Decimal, int]:
    start, end = local_day_bounds(local_today())
    query = select(func.coalesce(func.sum(SupplierOrder.cost_rub), 0), func.count()).where(
        SupplierOrder.created_at >= start,
        SupplierOrder.created_at < end,
        SupplierOrder.is_test.is_(False),
        SupplierOrder.status.in_(
            [SupplierOrderStatus.CREATED, SupplierOrderStatus.PENDING, SupplierOrderStatus.SUCCEEDED, SupplierOrderStatus.UNKNOWN]
        ),
    )
    if supplier_id is not None:
        query = query.where(SupplierOrder.supplier_id == supplier_id)
    total, count = (await session.execute(query)).one()
    return Decimal(total), int(count)


@dataclass
class PurchasePlan:
    supplier: Supplier
    supplier_product: SupplierProduct
    quantity: int  # units ordered from the supplier
    cost: Decimal | None  # supplier currency
    cost_rub: Decimal | None
    price_age: timedelta | None


async def plan_purchase(session: AsyncSession, item: OrderItem) -> PurchasePlan:
    product: Product = item.product
    if not product.preferred_supplier_product_id:
        raise ManualPurchaseRequired("Товар не связан с позицией поставщика")
    sp = await session.get(SupplierProduct, product.preferred_supplier_product_id)
    if sp is None or not sp.available:
        raise ManualPurchaseRequired("Позиция поставщика недоступна")
    supplier: Supplier = sp.supplier
    units = item.quantity * (product.supplier_quantity or 1)
    cost = None if sp.price is None else sp.price * Decimal(units) / Decimal(sp.price_unit or 1)
    cost_rub = None if cost is None else await fx.to_rub(session, cost, sp.currency)
    if cost_rub is not None:
        from .repricing import resolve_policy

        surcharge = supplier.fee_pct
        if sp.currency.upper() != "RUB":
            surcharge += (await resolve_policy(session, product)).conversion_fee_pct  # buying USD/TON for roubles
        if surcharge:
            cost_rub = money(cost_rub * (Decimal(100) + surcharge) / Decimal(100))
    age = utcnow() - sp.last_seen_at if sp.last_seen_at else None
    return PurchasePlan(supplier, sp, units if supplier.adapter == "smm_v2" else item.quantity, cost, cost_rub, age)


async def check_guards(session: AsyncSession, order: Order, item: OrderItem, plan: PurchasePlan, *, confirmed: bool, live: bool) -> None:
    """Raises Blocked / ManualPurchaseRequired / ConfirmationRequired."""
    from .repricing import resolve_policy

    supplier = plan.supplier
    product = item.product
    if await app_settings.automation_stopped(session):
        raise Blocked("Аварийная остановка автоматизации включена")
    if order.automation_paused:
        raise Blocked("Автоматизация по заказу приостановлена")
    if supplier.status is SupplierStatus.BLOCKED_BY_POLICY:
        raise Blocked(f"{supplier.name}: {supplier.status_reason}")
    if compliance_of(product) is not ComplianceStatus.APPROVED or plan.supplier_product.compliance_status is not ComplianceStatus.APPROVED:
        raise Blocked("Товар или услуга поставщика не одобрены по правилам платформы — закупка заблокирована")
    adapter_cls = registry.adapter_class(supplier.adapter)
    if supplier.purchase_mode is PurchaseMode.MONITOR:
        raise ManualPurchaseRequired(f"{supplier.name}: режим «только мониторинг» — закупите вручную")
    if supplier.purchase_mode is PurchaseMode.MANUAL or not adapter_cls.capabilities.purchase:
        raise ManualPurchaseRequired(f"{supplier.name}: ручная закупка")
    if live and supplier.status is not SupplierStatus.CONNECTED:
        raise ManualPurchaseRequired(f"{supplier.name}: поставщик не подключён ({supplier.status_reason or supplier.status.value})")
    policy = await resolve_policy(session, product)
    if plan.cost_rub is None:
        raise ManualPurchaseRequired("Неизвестна стоимость закупки (нет цены или курса)")
    if plan.price_age is None or plan.price_age > timedelta(minutes=policy.max_price_age_minutes):
        raise Blocked(f"Цена поставщика устарела (старше {policy.max_price_age_minutes} мин) — обновите каталог")
    if supplier.max_single_purchase > 0 and plan.cost_rub > supplier.max_single_purchase:
        raise Blocked(f"Сумма {fmt_money(plan.cost_rub)} больше лимита одной закупки {fmt_money(supplier.max_single_purchase)}")
    spent, count = await spent_today(session, supplier.id)
    if supplier.daily_limit > 0 and spent + plan.cost_rub > supplier.daily_limit:
        raise Blocked(f"Суточный лимит {fmt_money(supplier.daily_limit)} будет превышен (уже {fmt_money(spent)})")
    if supplier.max_operations_per_day and count >= supplier.max_operations_per_day:
        raise Blocked(f"Достигнут лимит операций в сутки: {supplier.max_operations_per_day}")
    if live and supplier.balance is not None and supplier.balance_currency:
        bal_rub = await fx.to_rub(session, supplier.balance, supplier.balance_currency)
        if bal_rub is not None and bal_rub < plan.cost_rub:
            raise Blocked(f"Недостаточно средств у поставщика: баланс {fmt_money(bal_rub)}")
    sale = item.unit_price * item.quantity
    fee = sale * product.category.marketplace_commission_pct / Decimal(100)
    profit = sale - fee - plan.cost_rub
    loss = profit < policy.min_profit_rub
    automatic = supplier.purchase_mode is PurchaseMode.AUTO and product.auto_purchase_allowed
    if automatic:
        if loss:
            raise ConfirmationRequired(
                f"Прибыль {fmt_money(money(profit))} ниже минимума — автоматическая закупка остановлена", plan.cost_rub
            )
        if policy.max_purchase_budget_rub <= 0:
            raise ConfirmationRequired("Бюджет автоматических закупок не задан (0 ₽) — нужно подтверждение", plan.cost_rub)
        total_spent, _ = await spent_today(session)
        if total_spent + plan.cost_rub > policy.max_purchase_budget_rub:
            raise ConfirmationRequired(f"Дневной бюджет автозакупок {fmt_money(policy.max_purchase_budget_rub)} исчерпан", plan.cost_rub)
        return
    if not confirmed:
        warn = f" ⚠️ Прибыль {fmt_money(money(profit))} ниже минимума." if loss else ""
        raise ConfirmationRequired(f"Нужно подтверждение закупки на {fmt_money(plan.cost_rub)}.{warn}", plan.cost_rub)


def _simulate(plan: PurchasePlan, item: OrderItem) -> PurchaseResult:
    codes = []
    if item.product.delivery_type is DeliveryType.CODE:
        codes = [f"TEST-{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}" for _ in range(item.quantity)]
    return PurchaseResult(
        SupplierOrderStatus.SUCCEEDED,
        external_id=f"test-{secrets.token_hex(4)}",
        cost=plan.cost,
        currency=plan.supplier_product.currency,
        codes=codes,
        message="Тестовый режим: закупка смоделирована, деньги не списаны",
    )


async def latest_for_item(session: AsyncSession, item_id: int) -> SupplierOrder | None:
    return (
        await session.execute(
            select(SupplierOrder).where(SupplierOrder.order_item_id == item_id).order_by(SupplierOrder.id.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def purchase_for_item(
    session: AsyncSession, order: Order, item: OrderItem, actor: Actor, *, confirmed: bool = False
) -> SupplierOrder:
    """Buy the goods for one order item (idempotent)."""
    from . import inventory

    previous = await latest_for_item(session, item.id)
    if previous is not None:
        if previous.status in (SupplierOrderStatus.SUCCEEDED, SupplierOrderStatus.PENDING):
            return previous
        if previous.status in (SupplierOrderStatus.UNKNOWN, SupplierOrderStatus.CREATED):
            raise Blocked("Предыдущая закупка по этой позиции не подтверждена — нужна сверка с поставщиком, повтор запрещён")
        if not confirmed:
            raise ConfirmationRequired("Предыдущая попытка закупки не удалась — повтор только после подтверждения", None)
    live = await app_settings.is_live(session) and not order.is_test
    plan = await plan_purchase(session, item)
    await check_guards(session, order, item, plan, confirmed=confirmed, live=live)

    attempt = 1 + (await session.execute(select(func.count()).where(SupplierOrder.order_item_id == item.id))).scalar_one()
    key = f"oi:{item.id}:a{attempt}"
    request_payload = {"external_product_id": plan.supplier_product.external_id, "quantity": plan.quantity, "buyer_data": order.buyer_data}
    # 1) commit the intent first, in its own transaction
    async with session_scope() as intent:
        so = SupplierOrder(
            supplier_id=plan.supplier.id,
            supplier_product_id=plan.supplier_product.id,
            order_item_id=item.id,
            idempotency_key=key,
            status=SupplierOrderStatus.CREATED,
            quantity=plan.quantity,
            cost=plan.cost,
            currency=plan.supplier_product.currency,
            cost_rub=plan.cost_rub,
            is_test=not live,
            request=scrub(request_payload),
            attempts=1,
            confirmed_by=actor.label if confirmed else None,
        )
        intent.add(so)
        await intent.flush()
        so_id = so.id
    # 2) call the supplier (or simulate)
    if live:
        adapter = await build_adapter(session, plan.supplier)
        try:
            result = await adapter.purchase(
                PurchaseRequest(key, plan.supplier_product.external_id, plan.quantity, plan.cost, buyer_data=dict(order.buyer_data or {}))
            )
        except PurchaseNotSupported as exc:
            result = PurchaseResult(SupplierOrderStatus.FAILED, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - unexpected adapter error: outcome unknown
            result = PurchaseResult(SupplierOrderStatus.UNKNOWN, message=scrub_text(f"{type(exc).__name__}: {exc}"))
    else:
        result = _simulate(plan, item)
    # 3) record the outcome
    so = await session.get(SupplierOrder, so_id, with_for_update=True)
    assert so is not None
    so.status = result.status
    so.external_id = result.external_id
    so.response = scrub({"message": result.message, **result.raw})
    so.last_error = None if result.status in (SupplierOrderStatus.SUCCEEDED, SupplierOrderStatus.PENDING) else result.message[:2000]
    if result.cost is not None:
        so.cost = result.cost
        so.currency = result.currency or so.currency
        so.cost_rub = await fx.to_rub(session, result.cost, so.currency) or so.cost_rub
    supplier = plan.supplier
    if result.status in (SupplierOrderStatus.SUCCEEDED, SupplierOrderStatus.PENDING):
        supplier.success_count += 1
    elif result.status is SupplierOrderStatus.FAILED:
        supplier.error_count += 1
        supplier.last_error = result.message[:2000]
    if result.codes:
        unit_cost = money(so.cost_rub / Decimal(len(result.codes))) if so.cost_rub is not None else None
        imported = await inventory.add_codes(
            session,
            item.product,
            result.codes,
            SYSTEM,
            unit_cost=unit_cost,
            source=f"supplier:{supplier.code}",
            is_test=so.is_test,
            supplier_order_id=so.id,
            reserve_for=item,
        )
        result.codes.clear()  # drop plain codes from memory as soon as they are stored encrypted
        if imported.duplicates:
            so.status = SupplierOrderStatus.UNKNOWN
            so.last_error = f"Поставщик вернул {imported.duplicates} код(ов), которые уже есть в базе — проверьте вручную"
    if so.cost_rub is not None and item.unit_cost is None:
        item.unit_cost = money(so.cost_rub / Decimal(item.quantity))
    await audit(
        session,
        actor,
        "supplier.purchase",
        entity_type="supplier_order",
        entity_id=so.id,
        details={"order": order.number, "status": so.status.value, "test": so.is_test, "cost_rub": str(so.cost_rub)},
    )
    return so


async def record_manual_purchase(
    session: AsyncSession, order: Order, item: OrderItem, actor: Actor, *, cost_rub: Decimal, supplier_code: str = "manual", note: str = ""
) -> SupplierOrder:
    previous = await latest_for_item(session, item.id)
    if previous is not None and previous.status is SupplierOrderStatus.SUCCEEDED:
        raise Conflict("Закупка по этой позиции уже отмечена")
    supplier = await get_supplier(session, supplier_code)
    attempt = 1 + (await session.execute(select(func.count()).where(SupplierOrder.order_item_id == item.id))).scalar_one()
    so = SupplierOrder(
        supplier_id=supplier.id,
        order_item_id=item.id,
        idempotency_key=f"oi:{item.id}:m{attempt}",
        status=SupplierOrderStatus.SUCCEEDED,
        quantity=item.quantity,
        cost=money(cost_rub),
        currency="RUB",
        cost_rub=money(cost_rub),
        is_test=order.is_test,
        request={"manual": True, "note": note[:500]},
        confirmed_by=actor.label,
    )
    session.add(so)
    item.unit_cost = money(Decimal(cost_rub) / Decimal(item.quantity))
    await session.flush()
    await audit(
        session,
        actor,
        "supplier.manual_purchase",
        entity_type="supplier_order",
        entity_id=so.id,
        details={"order": order.number, "cost_rub": str(cost_rub)},
    )
    return so


async def poll(session: AsyncSession, so: SupplierOrder) -> SupplierOrder:
    """Update a PENDING order, reconcile UNKNOWN/stale CREATED ones."""
    supplier = await session.get(Supplier, so.supplier_id)
    assert supplier is not None
    if so.is_test:
        return so
    adapter = await build_adapter(session, supplier)
    try:
        if so.status is SupplierOrderStatus.PENDING and so.external_id:
            result = await adapter.order_status(so.external_id)
        elif so.status in (SupplierOrderStatus.UNKNOWN, SupplierOrderStatus.CREATED):
            if so.status is SupplierOrderStatus.CREATED and utcnow() - so.created_at < UNKNOWN_AFTER:
                return so
            so.status = SupplierOrderStatus.UNKNOWN
            found = await adapter.find_by_key(so.idempotency_key) if adapter.capabilities.reconcile_by_key else None
            if found is None:
                return so
            result = found
        else:
            return so
    except (IntegrationError, PurchaseNotSupported) as exc:
        so.last_error = scrub_text(str(exc))[:2000]
        return so
    so.status = result.status
    so.external_id = result.external_id or so.external_id
    so.response = scrub({"message": result.message, **result.raw})
    if result.codes and so.order_item_id:
        from . import inventory

        item = await session.get(OrderItem, so.order_item_id)
        if item is not None:
            await inventory.add_codes(
                session, item.product, result.codes, SYSTEM, source=f"supplier:{supplier.code}", supplier_order_id=so.id, reserve_for=item
            )
            result.codes.clear()
    return so


async def sync_all(session: AsyncSession) -> list[SyncRun]:
    runs = []
    for supplier in (await session.execute(select(Supplier))).scalars():
        run = await sync_catalog(session, supplier)
        if run is not None:
            runs.append(run)
    return runs


async def check_all(session: AsyncSession) -> dict[str, bool]:
    out = {}
    for supplier in (await session.execute(select(Supplier))).scalars():
        if supplier.status in (SupplierStatus.BLOCKED_BY_POLICY, SupplierStatus.DISABLED):
            continue
        out[supplier.code] = (await check_connection(session, supplier)).ok
    return out
