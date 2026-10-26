"""Shop analytics built only from recorded data.

Money comes from the transaction ledger written when a deal completes
(services/orders.finalize). Metrics that need data the integration does not
provide (views → conversion, the PlayerOK shop rating) are returned as
``None`` with the reason instead of an estimate. Test orders are excluded
unless asked for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import LogResult, OrderStatus, SupplierOrderStatus, SyncStatus, TransactionKind
from ..database.models import (
    AutomationLog,
    Order,
    OrderEvent,
    OrderItem,
    Product,
    ProductCategory,
    Review,
    Supplier,
    SupplierOrder,
    SupplierPriceHistory,
    SyncRun,
    Transaction,
)
from ..integrations.marketplace.playerok_manual import get_marketplace
from ..shared.errors import DomainError
from ..shared.money import ZERO, money
from ..shared.timeutil import local_day_bounds, local_today
from . import sync

PERIODS = {"today": "Сегодня", "yesterday": "Вчера", "7d": "7 дней", "30d": "30 дней", "90d": "90 дней"}


@dataclass(frozen=True)
class Period:
    code: str
    label: str
    start: datetime
    end: datetime
    first_day: date
    last_day: date


def period(code: str = "30d", start: date | None = None, end: date | None = None) -> Period:
    today = local_today()
    if code == "custom":
        if start is None or end is None or start > end:
            raise DomainError("Укажите корректный период: начало не позже конца")
        if (end - start).days > 731:
            raise DomainError("Период не длиннее двух лет")
        first, last = start, end
        label = f"{start:%d.%m.%Y} — {end:%d.%m.%Y}"
    elif code == "today":
        first = last = today
        label = PERIODS[code]
    elif code == "yesterday":
        first = last = today - timedelta(days=1)
        label = PERIODS[code]
    elif code in ("7d", "30d", "90d"):
        days = int(code[:-1])
        first, last = today - timedelta(days=days - 1), today
        label = PERIODS[code]
    else:
        raise DomainError("Неизвестный период")
    return Period(code, label, local_day_bounds(first)[0], local_day_bounds(last)[1], first, last)


def _orders_filter(stmt: Select, include_test: bool) -> Select:
    return stmt if include_test else stmt.where(Order.is_test.is_(False))


async def _ledger(session: AsyncSession, p: Period, include_test: bool) -> dict[str, Decimal]:
    stmt = select(Transaction.kind, func.coalesce(func.sum(Transaction.amount_rub), 0)).where(
        Transaction.occurred_at >= p.start, Transaction.occurred_at < p.end
    )
    if not include_test:
        stmt = stmt.where(Transaction.is_test.is_(False))
    rows = dict((await session.execute(stmt.group_by(Transaction.kind))).all())
    return {k.value: Decimal(rows.get(k, 0)) for k in TransactionKind}


async def _event_count(session: AsyncSession, p: Period, status: OrderStatus, include_test: bool) -> int:
    stmt = (
        select(func.count(distinct(OrderEvent.order_id)))
        .join(Order, Order.id == OrderEvent.order_id)
        .where(OrderEvent.to_status == status.value, OrderEvent.created_at >= p.start, OrderEvent.created_at < p.end)
    )
    return (await session.execute(_orders_filter(stmt, include_test))).scalar_one()


async def metrics(session: AsyncSession, p: Period, *, include_test: bool = False) -> dict[str, Any]:
    ledger = await _ledger(session, p, include_test)
    placed = (
        await session.execute(_orders_filter(select(func.count()).where(Order.placed_at >= p.start, Order.placed_at < p.end), include_test))
    ).scalar_one()
    completed_q = _orders_filter(
        select(Order).where(Order.status == OrderStatus.COMPLETED, Order.completed_at >= p.start, Order.completed_at < p.end), include_test
    )
    completed_orders = (await session.execute(completed_q)).scalars().all()
    completed = len(completed_orders)
    without_cost = sum(1 for o in completed_orders if o.cost_total is None)
    revenue = ledger["sale"]
    fees = -(ledger["marketplace_fee"] + ledger["payment_fee"] + ledger["supplier_fee"])
    costs = -ledger["purchase"]
    refunds_amount = -ledger["refund"]
    net = revenue - fees - costs - refunds_amount + ledger["adjustment"]
    revenue_with_cost = sum((o.total_amount for o in completed_orders if o.cost_total is not None), ZERO)
    net_known = sum((o.net_profit for o in completed_orders if o.net_profit is not None), ZERO) - refunds_amount
    processing = (
        await session.execute(
            _orders_filter(
                select(func.avg(func.extract("epoch", Order.delivered_at - Order.placed_at))).where(
                    Order.delivered_at >= p.start, Order.delivered_at < p.end
                ),
                include_test,
            )
        )
    ).scalar_one()
    review_stmt = select(func.count(), func.avg(Review.rating)).where(Review.created_at >= p.start, Review.created_at < p.end)
    reviews, avg_rating = (await session.execute(review_stmt)).one()
    ready_events = (
        await session.execute(
            _orders_filter(
                select(OrderEvent.actor, func.count(distinct(OrderEvent.order_id)))
                .join(Order, Order.id == OrderEvent.order_id)
                .where(
                    OrderEvent.to_status == OrderStatus.READY_FOR_DELIVERY.value,
                    OrderEvent.created_at >= p.start,
                    OrderEvent.created_at < p.end,
                )
                .group_by(OrderEvent.actor),
                include_test,
            )
        )
    ).all()
    auto_ready = sum(c for actor, c in ready_events if actor == "система")
    all_ready = sum(c for _, c in ready_events)
    auto_ops = dict(
        (
            await session.execute(
                select(AutomationLog.result, func.count())
                .where(AutomationLog.created_at >= p.start, AutomationLog.created_at < p.end)
                .group_by(AutomationLog.result)
            )
        ).all()
    )
    sync_failed = (
        await session.execute(
            select(func.count()).where(SyncRun.started_at >= p.start, SyncRun.started_at < p.end, SyncRun.status == SyncStatus.FAILED)
        )
    ).scalar_one()
    so_failed = (
        await session.execute(
            select(func.count()).where(
                SupplierOrder.created_at >= p.start,
                SupplierOrder.created_at < p.end,
                SupplierOrder.status.in_([SupplierOrderStatus.FAILED, SupplierOrderStatus.UNKNOWN]),
            )
        )
    ).scalar_one()
    market = get_marketplace()
    return {
        "period": {"code": p.code, "label": p.label, "from": p.first_day.isoformat(), "to": p.last_day.isoformat()},
        "include_test": include_test,
        "orders": placed,
        "completed": completed,
        "cancelled": await _event_count(session, p, OrderStatus.CANCELLED, include_test),
        "refunds": await _event_count(session, p, OrderStatus.REFUND, include_test),
        "disputes": await _event_count(session, p, OrderStatus.DISPUTE, include_test),
        "reviews": reviews,
        "avg_review_rating": None if avg_rating is None else round(float(avg_rating), 2),
        "shop_rating": None,
        "shop_rating_note": market.reason("fetch_reviews") if not market.supports("fetch_reviews") else "",
        "revenue": str(money(revenue)),
        "purchase_costs": str(money(costs)),
        "fees": str(money(fees)),
        "refunds_amount": str(money(refunds_amount)),
        "net_profit": str(money(net)),
        "net_profit_known": str(money(net_known)),
        "orders_without_cost": without_cost,
        "margin_pct": None if revenue_with_cost <= 0 else str(money(net_known / revenue_with_cost * 100)),
        "avg_check": None if completed == 0 else str(money(revenue / completed)),
        "avg_processing_minutes": None if processing is None else round(float(processing) / 60, 1),
        "conversion": None,
        "conversion_note": "Нет данных о просмотрах объявлений: PlayerOK не отдаёт статистику без API",
        "automation_ops": {k.value: auto_ops.get(k, 0) for k in LogResult},
        "auto_ready_share": None if all_ready == 0 else round(auto_ready / all_ready * 100, 1),
        "integration_errors": sync_failed + so_failed + auto_ops.get(LogResult.ERROR, 0),
    }


async def timeseries(session: AsyncSession, p: Period, *, include_test: bool = False) -> list[dict[str, Any]]:
    tz = get_settings().display_timezone
    day = func.date(func.timezone(tz, Transaction.occurred_at))
    stmt = select(
        day.label("day"),
        func.coalesce(func.sum(case((Transaction.kind == TransactionKind.SALE, Transaction.amount_rub), else_=0)), 0),
        func.coalesce(func.sum(Transaction.amount_rub), 0),
    ).where(Transaction.occurred_at >= p.start, Transaction.occurred_at < p.end)
    if not include_test:
        stmt = stmt.where(Transaction.is_test.is_(False))
    money_rows = {r[0]: (r[1], r[2]) for r in (await session.execute(stmt.group_by(day)))}
    oday = func.date(func.timezone(tz, Order.placed_at))
    ostmt = _orders_filter(
        select(oday, func.count()).where(Order.placed_at >= p.start, Order.placed_at < p.end).group_by(oday), include_test
    )
    order_rows = dict((await session.execute(ostmt)).all())
    out = []
    current = p.first_day
    while current <= p.last_day:
        revenue, net = money_rows.get(current, (0, 0))
        out.append(
            {
                "day": current.isoformat(),
                "revenue": str(money(Decimal(revenue))),
                "net_profit": str(money(Decimal(net))),
                "orders": order_rows.get(current, 0),
            }
        )
        current += timedelta(days=1)
    return out


async def breakdown(session: AsyncSession, p: Period, *, include_test: bool = False) -> dict[str, Any]:
    base = (
        select(
            Product.id,
            Product.name,
            ProductCategory.name.label("category"),
            func.sum(OrderItem.quantity).label("qty"),
            func.sum(OrderItem.unit_price * OrderItem.quantity).label("revenue"),
            func.sum(
                case(
                    (
                        OrderItem.unit_cost.is_not(None),
                        OrderItem.unit_price * OrderItem.quantity * (1 - ProductCategory.marketplace_commission_pct / 100)
                        - OrderItem.unit_cost * OrderItem.quantity,
                    ),
                    else_=None,
                )
            ).label("profit"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .where(Order.status == OrderStatus.COMPLETED, Order.completed_at >= p.start, Order.completed_at < p.end)
    )
    base = _orders_filter(base, include_test)
    products = [
        {
            "product_id": r.id,
            "name": r.name,
            "category": r.category,
            "quantity": int(r.qty or 0),
            "revenue": str(money(Decimal(r.revenue or 0))),
            "profit_before_withdrawal": None if r.profit is None else str(money(Decimal(r.profit))),
        }
        for r in (await session.execute(base.group_by(Product.id, Product.name, ProductCategory.name)))
    ]
    categories: dict[str, dict[str, Any]] = {}
    for row in products:
        cat = categories.setdefault(
            row["category"], {"category": row["category"], "quantity": 0, "revenue": Decimal(0), "profit": Decimal(0)}
        )
        cat["quantity"] += row["quantity"]
        cat["revenue"] += Decimal(row["revenue"])
        if row["profit_before_withdrawal"] is not None:
            cat["profit"] += Decimal(row["profit_before_withdrawal"])
    supplier_rows = (
        await session.execute(
            select(
                Supplier.name,
                func.count(),
                func.count().filter(SupplierOrder.status == SupplierOrderStatus.SUCCEEDED),
                func.count().filter(SupplierOrder.status.in_([SupplierOrderStatus.FAILED, SupplierOrderStatus.UNKNOWN])),
                func.coalesce(func.sum(SupplierOrder.cost_rub), 0),
            )
            .join(Supplier, Supplier.id == SupplierOrder.supplier_id)
            .where(
                SupplierOrder.created_at >= p.start,
                SupplierOrder.created_at < p.end,
                *(() if include_test else (SupplierOrder.is_test.is_(False),)),
            )
            .group_by(Supplier.name)
        )
    ).all()
    return {
        "products": products,
        "top_profit": sorted(
            [x for x in products if x["profit_before_withdrawal"] is not None],
            key=lambda x: Decimal(x["profit_before_withdrawal"]),
            reverse=True,
        )[:10],
        "top_revenue": sorted(products, key=lambda x: Decimal(x["revenue"]), reverse=True)[:10],
        "categories": [{**c, "revenue": str(money(c["revenue"])), "profit": str(money(c["profit"]))} for c in categories.values()],
        "suppliers": [
            {
                "supplier": name,
                "orders": total,
                "succeeded": ok,
                "failed": bad,
                "spend_rub": str(money(Decimal(spend))),
                "success_rate": round(ok / total * 100, 1) if total else None,
            }
            for name, total, ok, bad, spend in supplier_rows
        ],
    }


async def price_dynamics(session: AsyncSession, product_id: int, days: int = 30) -> dict[str, Any]:
    from ..database.models import Listing, ListingRevision

    product = await session.get(Product, product_id)
    since = local_day_bounds(local_today() - timedelta(days=days - 1))[0]
    purchase = []
    if product is not None and product.preferred_supplier_product_id:
        rows = (
            await session.execute(
                select(
                    SupplierPriceHistory.captured_at,
                    SupplierPriceHistory.price,
                    SupplierPriceHistory.currency,
                    SupplierPriceHistory.price_rub,
                )
                .where(
                    SupplierPriceHistory.supplier_product_id == product.preferred_supplier_product_id,
                    SupplierPriceHistory.captured_at >= since,
                )
                .order_by(SupplierPriceHistory.captured_at)
            )
        ).all()
        purchase = [
            {"at": r[0].isoformat(), "price": str(r[1]), "currency": r[2], "price_rub": None if r[3] is None else str(r[3])} for r in rows
        ]
    sale_rows = (
        await session.execute(
            select(ListingRevision.created_at, ListingRevision.snapshot)
            .join(Listing, Listing.id == ListingRevision.listing_id)
            .where(Listing.product_id == product_id, ListingRevision.created_at >= since)
            .order_by(ListingRevision.created_at)
        )
    ).all()
    sale = [{"at": r[0].isoformat(), "price": r[1].get("price")} for r in sale_rows]
    return {"purchase": purchase, "sale": sale}


async def sync_overview(session: AsyncSession) -> list[dict[str, Any]]:
    runs = await sync.latest_by_source(session)
    since = local_day_bounds(local_today())[0]
    errors_today = dict(
        (
            await session.execute(
                select(SyncRun.source, func.count())
                .where(SyncRun.started_at >= since, SyncRun.status == SyncStatus.FAILED)
                .group_by(SyncRun.source)
            )
        ).all()
    )
    out = [
        {
            "source": r.source,
            "kind": r.kind,
            "status": r.status.value,
            "received": r.records_received,
            "saved": r.records_saved,
            "errors": r.errors_count,
            "errors_today": errors_today.get(r.source, 0),
            "message": r.message,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in runs
    ]
    market = get_marketplace()
    out.insert(
        0,
        {
            "source": "playerok",
            "kind": "orders",
            "status": "unavailable" if not market.supports("fetch_orders") else "unknown",
            "received": 0,
            "saved": 0,
            "errors": 0,
            "errors_today": 0,
            "message": market.reason("fetch_orders"),
            "started_at": None,
            "finished_at": None,
        },
    )
    return out


async def recorded_totals(session: AsyncSession) -> dict[str, Any]:
    """«Данные загружены»: how many records the system holds and their sources."""
    deals = (await session.execute(select(func.count()).where(Order.is_test.is_(False)))).scalar_one()
    by_source = dict(
        (await session.execute(select(Order.source, func.count()).where(Order.is_test.is_(False)).group_by(Order.source))).all()
    )
    reviews = (await session.execute(select(func.count(Review.id)))).scalar_one()
    txs = (await session.execute(select(func.count()).where(Transaction.is_test.is_(False)))).scalar_one()
    last = (await session.execute(select(func.max(Order.updated_at)).where(Order.is_test.is_(False)))).scalar_one()
    return {
        "deals": deals,
        "deals_by_source": by_source,
        "reviews": reviews,
        "transactions": txs,
        "last_update": last.isoformat() if last else None,
    }
