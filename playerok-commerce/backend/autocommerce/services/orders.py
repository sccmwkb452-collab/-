"""Order Manager.

Lifecycle: detection → id/status check → reservation → supplier availability
→ purchase (if allowed and needed) → code/service → verification → delivery
→ cost and profit → history → notification → error handling.

Guarantees:

* one order per (marketplace, external id): creation is
  ``INSERT … ON CONFLICT DO NOTHING``; a repeated import or a double click
  returns the existing order and never processes it twice;
* processing takes a row lock on the order and the order row is versioned,
  so two workers cannot advance the same order concurrently;
* purchases are idempotent per order item (services/suppliers.py), codes are
  reserved under ``SKIP LOCKED`` and bound to one order item
  (services/inventory.py);
* anything dangerous or unverifiable stops the order in a waiting status
  and notifies the owner; the operator can intervene at any moment.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import (
    ORDER_STATUS_LABELS,
    DeliveryType,
    LogResult,
    OrderStatus,
    Severity,
    SupplierOrderStatus,
    TransactionKind,
)
from ..database.models import Listing, Order, OrderEvent, OrderItem, Product, Transaction
from ..integrations.marketplace.playerok_manual import get_marketplace
from ..shared.errors import Blocked, Conflict, DomainError, NotFound
from ..shared.money import fmt_money, money
from ..shared.timeutil import utcnow
from . import app_settings, hints, inventory, jobs, suppliers
from .audit import SYSTEM, Actor, audit, automation_log
from .autosettings import is_active
from .catalog import compliance_problem, get_product, product_by_sku
from .notifications import Button, btn, esc, notify
from .repricing import resolve_policy

S = OrderStatus

TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    S.NEW: {
        S.PENDING_REVIEW,
        S.PENDING_PURCHASE,
        S.PENDING_CONFIRMATION,
        S.PROCESSING,
        S.READY_FOR_DELIVERY,
        S.ERROR,
        S.CANCELLED,
        S.DISPUTE,
    },
    S.PENDING_REVIEW: {
        S.NEW,
        S.PENDING_PURCHASE,
        S.PENDING_CONFIRMATION,
        S.PROCESSING,
        S.READY_FOR_DELIVERY,
        S.ERROR,
        S.CANCELLED,
        S.DISPUTE,
        S.REFUND,
    },
    S.PENDING_PURCHASE: {
        S.PROCESSING,
        S.READY_FOR_DELIVERY,
        S.PENDING_CONFIRMATION,
        S.PENDING_REVIEW,
        S.ERROR,
        S.CANCELLED,
        S.DISPUTE,
        S.REFUND,
    },
    S.PENDING_CONFIRMATION: {
        S.PROCESSING,
        S.READY_FOR_DELIVERY,
        S.PENDING_PURCHASE,
        S.PENDING_REVIEW,
        S.ERROR,
        S.CANCELLED,
        S.DISPUTE,
        S.REFUND,
    },
    S.PROCESSING: {S.READY_FOR_DELIVERY, S.PENDING_PURCHASE, S.PENDING_REVIEW, S.ERROR, S.DISPUTE, S.REFUND, S.CANCELLED},
    S.READY_FOR_DELIVERY: {S.DELIVERED, S.PENDING_REVIEW, S.ERROR, S.DISPUTE, S.REFUND, S.CANCELLED},
    S.DELIVERED: {S.COMPLETED, S.DISPUTE, S.REFUND, S.ERROR},
    S.COMPLETED: {S.REFUND, S.DISPUTE},
    S.ERROR: {S.NEW, S.PENDING_REVIEW, S.PENDING_PURCHASE, S.PROCESSING, S.READY_FOR_DELIVERY, S.CANCELLED, S.REFUND, S.DISPUTE},
    S.DISPUTE: {S.COMPLETED, S.REFUND, S.DELIVERED, S.READY_FOR_DELIVERY, S.CANCELLED, S.ERROR},
    S.REFUND: set(),
    S.CANCELLED: set(),
}
ACTIVE = (S.NEW, S.PENDING_PURCHASE, S.PROCESSING)  # statuses the pipeline advances on its own
FINAL = (S.COMPLETED, S.REFUND, S.CANCELLED)


@dataclass
class NewItem:
    product: int | str  # id or SKU
    quantity: int
    unit_price: Decimal


@dataclass
class NewOrder:
    external_id: str
    items: list[NewItem]
    buyer_name: str | None = None
    buyer_data: dict[str, Any] = field(default_factory=dict)
    placed_at: datetime | None = None
    marketplace: str = "playerok"
    source: str = "manual"
    notes: str = ""
    is_test: bool | None = None


async def get_order(session: AsyncSession, order_id: int, *, lock: bool = False) -> Order:
    query = select(Order).where(Order.id == order_id)
    if lock:
        query = query.with_for_update(of=Order).execution_options(populate_existing=True)
    order = (await session.execute(query)).scalar_one_or_none()
    if order is None:
        raise NotFound("Заказ не найден")
    if lock:
        await session.refresh(order, ["items"])
    return order


async def find_order(session: AsyncSession, ref: str) -> Order | None:
    ref = ref.strip()
    return (
        await session.execute(select(Order).where(or_(Order.number == ref.upper(), Order.external_id == ref)).limit(1))
    ).scalar_one_or_none()


async def _event(session: AsyncSession, order: Order, actor: Actor, message: str, *, to: OrderStatus | None = None, **details: Any) -> None:
    session.add(
        OrderEvent(
            order_id=order.id,
            from_status=order.status.value if to else None,
            to_status=to.value if to else None,
            actor=actor.label,
            message=message[:2000],
            details=details,
        )
    )


async def _move(session: AsyncSession, order: Order, to: OrderStatus, actor: Actor, reason: str = "", *, force: bool = False) -> None:
    if order.status is to:
        return
    if not force and to not in TRANSITIONS[order.status]:
        raise Conflict(f"Нельзя перевести заказ из «{ORDER_STATUS_LABELS[order.status]}» в «{ORDER_STATUS_LABELS[to]}»")
    await _event(session, order, actor, reason or ORDER_STATUS_LABELS[to], to=to)
    order.status = to
    order.status_reason = reason[:2000]
    order.needs_attention = to in (S.PENDING_REVIEW, S.PENDING_PURCHASE, S.PENDING_CONFIRMATION, S.ERROR, S.DISPUTE)
    if to in FINAL:
        order.needs_attention = False


def order_buttons(order: Order) -> list[list[Button]]:
    return [[btn("🛒 Открыть заказ", f"ord:open:{order.id}")]]


# ---------------------------------------------------------------------------
# creation and import
# ---------------------------------------------------------------------------


async def _resolve_product(session: AsyncSession, ref: int | str) -> Product:
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        return await get_product(session, int(ref))
    product = await product_by_sku(session, str(ref))
    if product is None:
        raise NotFound(f"Товар «{ref}» не найден")
    return product


async def create_order(session: AsyncSession, data: NewOrder, actor: Actor, *, process: bool = True) -> tuple[Order, bool]:
    external_id = data.external_id.strip()
    if not external_id or len(external_id) > 120:
        raise DomainError("Укажите номер сделки PlayerOK (до 120 символов)")
    if not data.items:
        raise DomainError("В заказе нет товаров")
    resolved: list[tuple[Product, NewItem]] = []
    for item in data.items:
        if item.quantity <= 0:
            raise DomainError("Количество должно быть больше нуля")
        if money(item.unit_price) <= 0:
            raise DomainError("Цена должна быть больше нуля")
        resolved.append((await _resolve_product(session, item.product), item))
    is_test = data.is_test if data.is_test is not None else not await app_settings.is_live(session)
    total = money(sum((money(i.unit_price) * i.quantity for _, i in resolved), Decimal(0)))
    stmt = (
        insert(Order)
        .values(
            marketplace=data.marketplace,
            external_id=external_id,
            source=data.source,
            buyer_name=(data.buyer_name or "").strip()[:120] or None,
            buyer_data={k: str(v)[:500] for k, v in (data.buyer_data or {}).items() if v},
            status=S.NEW,
            total_amount=total,
            currency="RUB",
            is_test=is_test,
            placed_at=data.placed_at or utcnow(),
            notes=data.notes[:2000],
        )
        .on_conflict_do_nothing(constraint="uq_orders_marketplace_external")
        .returning(Order.id)
    )
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    if new_id is None:
        existing = (
            await session.execute(select(Order).where(Order.marketplace == data.marketplace, Order.external_id == external_id))
        ).scalar_one()
        await automation_log(
            session,
            "orders",
            "duplicate",
            LogResult.SKIPPED,
            f"Повтор сделки {external_id}: заказ {existing.number} уже есть",
            order_id=existing.id,
        )
        return existing, False
    for product, item in resolved:
        listing_id = (
            await session.execute(select(Listing.id).where(Listing.product_id == product.id).order_by(Listing.id.desc()).limit(1))
        ).scalar_one_or_none()
        session.add(
            OrderItem(
                order_id=new_id, product_id=product.id, listing_id=listing_id, quantity=item.quantity, unit_price=money(item.unit_price)
            )
        )
    await session.flush()
    order = await get_order(session, new_id)
    await session.refresh(order, ["items"])
    await _event(session, order, actor, f"Заказ создан ({data.source})", source=data.source)
    await audit(
        session, actor, "order.create", entity_type="order", entity_id=order.id, details={"external_id": external_id, "test": is_test}
    )
    lines = "\n".join(f"• {esc(i.product.name)} × {i.quantity} — {fmt_money(i.unit_price)}" for i in order.items)
    await notify(
        session,
        "order_new",
        f"Новый заказ {order.number}{' 🧪' if is_test else ''}",
        f"Сделка PlayerOK: <code>{esc(external_id)}</code>\nПокупатель: {esc(order.buyer_name or '—')}\n{lines}\nСумма: <b>{fmt_money(total)}</b>",
        severity=Severity.SUCCESS,
        buttons=order_buttons(order),
        entity_type="order",
        entity_id=order.id,
        dedupe_key=f"order_new:{order.id}",
    )
    if process and await app_settings.get_setting(session, "orders.auto_pipeline"):
        await jobs.enqueue(session, "order.process", {"order_id": order.id}, dedupe_key=f"order:{order.id}")
    return order, True


IMPORT_COLUMNS = ("external_id", "placed_at", "sku", "quantity", "unit_price", "buyer", "status", "unit_cost", "link")


def _parse_dt(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            from ..shared.timeutil import local_tz

            parsed = parsed.replace(tzinfo=local_tz())
        return parsed
    raise DomainError(f"Не удалось разобрать дату «{value}»")


async def import_csv(session: AsyncSession, content: str, actor: Actor) -> dict[str, Any]:
    """Import historical or new deals. Columns: external_id, placed_at, sku,
    quantity, unit_price, buyer, status (new|completed|cancelled|refund),
    unit_cost, link. Repeated rows are skipped (idempotency)."""
    reader = csv.DictReader(io.StringIO(content.lstrip("﻿")), delimiter=";" if content.count(";") > content.count(",") else ",")
    missing = {"external_id", "sku", "unit_price"} - set(reader.fieldnames or [])
    if missing:
        raise DomainError("В CSV нет колонок: " + ", ".join(sorted(missing)))
    stats = {"rows": 0, "created": 0, "duplicates": 0, "errors": 0, "messages": []}
    for line_no, row in enumerate(reader, start=2):
        stats["rows"] += 1
        try:
            async with session.begin_nested():
                status = (row.get("status") or "new").strip().lower()
                order, created = await create_order(
                    session,
                    NewOrder(
                        external_id=row["external_id"],
                        items=[NewItem(row["sku"].strip(), int(row.get("quantity") or 1), money(row["unit_price"]))],
                        buyer_name=row.get("buyer"),
                        buyer_data={"link": row.get("link") or ""},
                        placed_at=_parse_dt(row.get("placed_at", "")),
                        source="import",
                        is_test=False,
                    ),
                    actor,
                    process=status == "new",
                )
                if not created:
                    stats["duplicates"] += 1
                    continue
                stats["created"] += 1
                if row.get("unit_cost"):
                    for item in order.items:
                        item.unit_cost = money(row["unit_cost"])
                if status == "completed":
                    await _move(session, order, S.COMPLETED, actor, "Импорт: завершённая сделка", force=True)
                    order.delivered_at = order.buyer_confirmed_at = order.completed_at = order.placed_at
                    await finalize(session, order)
                elif status in ("cancelled", "refund"):
                    await _move(session, order, S.CANCELLED if status == "cancelled" else S.REFUND, actor, "Импорт", force=True)
        except (DomainError, ValueError, KeyError) as exc:
            stats["errors"] += 1
            if len(stats["messages"]) < 20:
                stats["messages"].append(f"Строка {line_no}: {getattr(exc, 'message', str(exc))}")
    await audit(session, actor, "orders.import", details={k: v for k, v in stats.items() if k != "messages"})
    return stats


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


async def _validate(session: AsyncSession, order: Order) -> list[str]:
    problems: list[str] = []
    for item in order.items:
        product = item.product
        problem = compliance_problem(product)
        if problem:
            problems.append(f"{product.name}: {problem}")
        if product.min_price is not None and item.unit_price < product.min_price:
            problems.append(
                f"{product.name}: продано за {fmt_money(item.unit_price)} — ниже минимальной цены {fmt_money(product.min_price)}"
            )
        needs_link = product.delivery_type is DeliveryType.SERVICE or "username" in (product.required_buyer_data or "")
        if needs_link and not (order.buyer_data or {}).get("link"):
            problems.append(f"{product.name}: нет данных от покупателя ({product.required_buyer_data or 'ссылка'})")
    return problems


async def _fulfil_item(session: AsyncSession, order: Order, item: OrderItem, actor: Actor, *, confirmed: bool) -> tuple[str, str]:
    """Returns (state, message): ready | waiting_supplier | manual | confirm | blocked | failed."""
    product = item.product
    if item.fulfilled_quantity >= item.quantity:
        return "ready", ""
    previous = await suppliers.latest_for_item(session, item.id)
    if product.delivery_type is DeliveryType.CODE:
        _, delivery_cfg = await is_active(session, "auto_delivery")
        await inventory.reserve(session, item, item.quantity, is_test=order.is_test)
        have = len(await inventory.assigned(session, item.id))
        if have >= item.quantity:
            item.fulfilled_quantity = item.quantity
            if item.unit_cost is None:
                costs = [c.unit_cost for c in await inventory.assigned(session, item.id) if c.unit_cost is not None]
                if len(costs) == item.quantity:
                    item.unit_cost = money(sum(costs, Decimal(0)) / Decimal(item.quantity))
            return "ready", ""
        if delivery_cfg.get("code_source") == "inventory":
            return "manual", f"На складе {have} из {item.quantity} кодов — пополните склад"
    elif previous is not None and previous.status is SupplierOrderStatus.SUCCEEDED:
        item.fulfilled_quantity = item.quantity
        return "ready", ""
    elif product.delivery_type is DeliveryType.MANUAL and not product.preferred_supplier_product_id:
        item.fulfilled_quantity = item.quantity
        if item.unit_cost is None and product.manual_unit_cost is not None:
            item.unit_cost = product.manual_unit_cost
        return "ready", "Ручная выдача"
    try:
        so = await suppliers.purchase_for_item(session, order, item, actor, confirmed=confirmed)
    except suppliers.ManualPurchaseRequired as exc:
        return "manual", exc.reason
    except suppliers.ConfirmationRequired as exc:
        return "confirm", exc.reason
    except Blocked as exc:
        return "blocked", exc.message
    if so.status is SupplierOrderStatus.SUCCEEDED:
        if product.delivery_type is DeliveryType.CODE:
            have = len(await inventory.assigned(session, item.id))
            if have < item.quantity:
                return "failed", f"Поставщик вернул {have} из {item.quantity} кодов"
        item.fulfilled_quantity = item.quantity
        return "ready", so.response.get("message", "")
    if so.status is SupplierOrderStatus.PENDING:
        return "waiting_supplier", f"Поставщик выполняет заказ {so.external_id or ''}".strip()
    if so.status is SupplierOrderStatus.UNKNOWN:
        return "blocked", f"Результат закупки неизвестен: {so.last_error or ''} Проверьте у поставщика — повтор запрещён"
    return "failed", so.last_error or "Поставщик отклонил заказ"


async def process(session: AsyncSession, order_id: int, actor: Actor = SYSTEM, *, confirmed: bool = False) -> Order:
    order = await get_order(session, order_id, lock=True)
    if order.status not in ACTIVE and not (confirmed and order.status in (S.PENDING_CONFIRMATION, S.PENDING_PURCHASE, S.ERROR)):
        return order
    if await app_settings.automation_stopped(session) and actor is SYSTEM:
        await automation_log(session, "orders", "process", LogResult.SKIPPED, "Аварийная остановка: заказ ждёт", order_id=order.id)
        return order
    if order.automation_paused and actor is SYSTEM:
        return order

    if order.status is S.NEW and not order.review_passed:
        problems = await _validate(session, order)
        if problems:
            await _move(session, order, S.PENDING_REVIEW, actor, "; ".join(problems))
            await notify(
                session,
                "order_attention",
                f"Заказ {order.number} требует проверки",
                "\n".join(f"• {esc(p)}" for p in problems),
                severity=Severity.WARNING,
                buttons=[
                    [btn("▶️ Продолжить обработку", f"ord:continue:{order.id}"), btn("✖️ Отменить", f"ord:cancel:{order.id}")],
                    *order_buttons(order),
                ],
                entity_type="order",
                entity_id=order.id,
            )
            return order
        order.review_passed = True

    states: list[tuple[OrderItem, str, str]] = []
    for item in order.items:
        state, message = await _fulfil_item(session, order, item, actor, confirmed=confirmed)
        states.append((item, state, message))
    kinds = {s for _, s, _ in states}
    summary = "; ".join(f"{i.product.name}: {m}" for i, s, m in states if m)

    if kinds == {"ready"}:
        await _move(session, order, S.READY_FOR_DELIVERY, actor, summary or "Товар готов к выдаче")
        await _announce_ready(session, order)
    elif "failed" in kinds or "blocked" in kinds:
        target = S.ERROR if "failed" in kinds else S.PENDING_REVIEW
        await _move(session, order, target, actor, summary, force=True)
        await notify(
            session,
            "order_attention",
            f"Заказ {order.number}: {'ошибка' if target is S.ERROR else 'остановлен защитой'}",
            esc(summary),
            severity=Severity.CRITICAL if target is S.ERROR else Severity.WARNING,
            buttons=[[btn("🔁 Повторить", f"ord:retry:{order.id}"), btn("⚖️ Спор", f"ord:dispute:{order.id}")], *order_buttons(order)],
            entity_type="order",
            entity_id=order.id,
        )
        await hints.suggest(
            session,
            "problem_text",
            "text",
            order,
            title=f"Проблема с заказом {order.number}",
            dedupe_key=f"problem:{order.id}:{target.value}",
        )
    elif "confirm" in kinds:
        await _move(session, order, S.PENDING_CONFIRMATION, actor, summary)
        await notify(
            session,
            "purchase_confirm",
            f"Подтвердите закупку: {order.number}",
            esc(summary),
            severity=Severity.WARNING,
            buttons=[[btn("✅ Закупить", f"ord:buy:{order.id}"), btn("🛒 Куплю вручную", f"ord:manual:{order.id}")], *order_buttons(order)],
            entity_type="order",
            entity_id=order.id,
            permission="suppliers.purchase",
        )
    elif "manual" in kinds:
        await _move(session, order, S.PENDING_PURCHASE, actor, summary)
        await notify(
            session,
            "manual_purchase",
            f"Требуется ручная закупка: {order.number}",
            esc(summary) + _buyer_data_hint(order),
            severity=Severity.WARNING,
            buttons=[
                [btn("✅ Закуплено", f"ord:bought:{order.id}"), btn("📥 Добавить коды", f"ord:codes:{order.id}")],
                *order_buttons(order),
            ],
            entity_type="order",
            entity_id=order.id,
            dedupe_key=f"manual_purchase:{order.id}:{order.version}",
        )
    else:  # waiting_supplier
        await _move(session, order, S.PROCESSING, actor, summary)
        await jobs.enqueue(
            session, "order.poll", {"order_id": order.id}, dedupe_key=f"poll:{order.id}", run_after=utcnow() + timedelta(minutes=2)
        )
    return order


def _buyer_data_hint(order: Order) -> str:
    data = {k: v for k, v in (order.buyer_data or {}).items() if not k.startswith("_")}
    if not data:
        return ""
    return "\n\nДанные покупателя:\n" + "\n".join(f"• {esc(k)}: <code>{esc(v)}</code>" for k, v in data.items())


async def _announce_ready(session: AsyncSession, order: Order) -> None:
    lines, buttons = [], []
    for item in order.items:
        codes = await inventory.assigned(session, item.id)
        if codes:
            lines.append(f"• {esc(item.product.name)}: " + ", ".join(esc(c.code_mask) for c in codes))
            buttons.extend([btn(f"👁 Код {c.code_mask[-4:]}", f"code:show:{c.id}")] for c in codes[:6])
        else:
            lines.append(f"• {esc(item.product.name)} × {item.quantity}")
    test = "\n🧪 Тестовый заказ: коды и закупки смоделированы." if order.is_test else ""
    await notify(
        session,
        "order_status",
        f"Готов к выдаче: {order.number}",
        "\n".join(lines) + _buyer_data_hint(order) + test + "\n\nПередайте товар покупателю на PlayerOK и нажмите «Выдано».",
        severity=Severity.SUCCESS,
        buttons=[*buttons, [btn("📤 Выдано покупателю", f"ord:delivered:{order.id}")], *order_buttons(order)],
        entity_type="order",
        entity_id=order.id,
        dedupe_key=f"ready:{order.id}",
    )
    await hints.suggest(
        session,
        "auto_delivery",
        "instruction",
        order,
        title=f"Выдача по заказу {order.number}",
        context={"instructions": "(код — кнопкой «Показать код»)"},
    )


async def poll(session: AsyncSession, order_id: int) -> Order:
    """Background check of supplier orders for PROCESSING orders."""
    order = await get_order(session, order_id, lock=True)
    if order.status is not S.PROCESSING:
        return order
    pending = False
    for item in order.items:
        so = await suppliers.latest_for_item(session, item.id)
        if so is None:
            continue
        await suppliers.poll(session, so)
        if so.status is SupplierOrderStatus.PENDING:
            pending = True
    if pending:
        await jobs.enqueue(
            session,
            "order.poll",
            {"order_id": order.id},
            dedupe_key=f"poll:{order.id}:{utcnow():%H%M}",
            run_after=utcnow() + timedelta(minutes=5),
        )
        return order
    order.status = S.NEW  # let the pipeline re-evaluate every item
    order.review_passed = True
    return await process(session, order.id)


# ---------------------------------------------------------------------------
# operator actions
# ---------------------------------------------------------------------------


async def continue_after_review(session: AsyncSession, order: Order, actor: Actor) -> Order:
    if order.status not in (S.PENDING_REVIEW, S.ERROR):
        raise Conflict("Заказ не ждёт проверки")
    order.review_passed = True
    await _move(session, order, S.NEW, actor, "Проверено оператором, продолжить обработку")
    await audit(session, actor, "order.continue", entity_type="order", entity_id=order.id)
    return await process(session, order.id, actor)


async def retry(session: AsyncSession, order: Order, actor: Actor) -> Order:
    if order.status not in (S.ERROR, S.PENDING_REVIEW, S.PENDING_PURCHASE):
        raise Conflict("Повтор доступен для заказов с ошибкой или на проверке")
    await _move(session, order, S.NEW, actor, "Повторная обработка", force=True)
    return await process(session, order.id, actor, confirmed=True)


async def confirm_purchase(session: AsyncSession, order: Order, actor: Actor) -> Order:
    if order.status is not S.PENDING_CONFIRMATION:
        raise Conflict("Заказ не ждёт подтверждения закупки")
    await audit(session, actor, "order.purchase_confirmed", entity_type="order", entity_id=order.id)
    return await process(session, order.id, actor, confirmed=True)


async def choose_manual_purchase(session: AsyncSession, order: Order, actor: Actor) -> Order:
    await _move(session, order, S.PENDING_PURCHASE, actor, "Оператор выбрал ручную закупку")
    return order


async def mark_purchased(
    session: AsyncSession, order: Order, actor: Actor, *, cost_rub: Decimal | None = None, item_id: int | None = None
) -> Order:
    if order.status not in (S.PENDING_PURCHASE, S.PENDING_CONFIRMATION, S.ERROR, S.PENDING_REVIEW):
        raise Conflict("Заказ не ждёт закупки")
    for item in order.items:
        if item_id and item.id != item_id:
            continue
        if item.product.delivery_type is DeliveryType.CODE:
            continue  # codes are added with add_codes
        estimate = cost_rub
        if estimate is None:
            try:
                estimate = (await suppliers.plan_purchase(session, item)).cost_rub
            except suppliers.ManualPurchaseRequired:
                estimate = None
            if estimate is None and item.product.manual_unit_cost is not None:
                estimate = money(item.product.manual_unit_cost * item.quantity)
        if estimate is None:
            raise DomainError("Укажите стоимость закупки — она нужна для расчёта прибыли")
        await suppliers.record_manual_purchase(session, order, item, actor, cost_rub=estimate)
        item.fulfilled_quantity = item.quantity
    order.review_passed = True
    await _move(session, order, S.NEW, actor, "Закупка выполнена вручную", force=True)
    return await process(session, order.id, actor, confirmed=True)


async def add_codes(
    session: AsyncSession, order: Order, item_id: int, codes: list[str], actor: Actor, *, unit_cost: Decimal | None
) -> dict[str, int]:
    item = next((i for i in order.items if i.id == item_id), None)
    if item is None:
        raise NotFound("Позиция заказа не найдена")
    if order.status in FINAL or order.status is S.DELIVERED:
        raise Conflict("Заказ уже выдан или закрыт")
    result = await inventory.add_codes(
        session, item.product, codes, actor, unit_cost=unit_cost, source="manual", is_test=order.is_test, reserve_for=item
    )
    if unit_cost is not None and item.unit_cost is None:
        item.unit_cost = money(unit_cost)
    order.review_passed = True
    if order.status is not S.NEW:
        await _move(session, order, S.NEW, actor, "Добавлены коды", force=True)
    await process(session, order.id, actor, confirmed=True)
    return {"added": result.added, "duplicates": result.duplicates, "rejected": result.rejected}


async def mark_delivered(session: AsyncSession, order: Order, actor: Actor) -> Order:
    if order.status not in (S.READY_FOR_DELIVERY, S.DISPUTE):
        raise Conflict("Выдать можно только заказ со статусом «Готов к выдаче»")
    for item in order.items:
        if item.product.delivery_type is DeliveryType.CODE:
            have = len(await inventory.assigned(session, item.id))
            if have < item.quantity:
                raise Conflict(f"{item.product.name}: закреплено {have} из {item.quantity} кодов — выдача невозможна")
            await inventory.issue(session, item)
    order.delivered_at = utcnow()
    await _move(session, order, S.DELIVERED, actor, "Товар передан покупателю")
    await audit(session, actor, "order.delivered", entity_type="order", entity_id=order.id)
    await automation_log(
        session, "auto_delivery", "delivered", LogResult.OK, f"Заказ {order.number} выдан ({actor.label})", order_id=order.id
    )
    await hints.suggest(session, "seller_confirm_text", "text", order, title=f"Заказ {order.number} выдан")
    active, cfg = await is_active(session, "confirm_reminder")
    if active:
        await jobs.enqueue(
            session,
            "order.reminder",
            {"order_id": order.id, "kind": "confirm", "n": 1},
            dedupe_key=f"reminder:confirm:{order.id}:1",
            run_after=utcnow() + timedelta(hours=int(cfg["delay_hours"])),
        )
    return order


async def finalize(session: AsyncSession, order: Order) -> Order:
    """Fix revenue, fees, costs and net profit (idempotent per order)."""
    policy = None
    sale_total = money(sum((i.unit_price * i.quantity for i in order.items), Decimal(0)))
    fee_total = Decimal(0)
    cost_total: Decimal | None = Decimal(0)
    for item in order.items:
        product = item.product
        if policy is None:
            policy = await resolve_policy(session, product)
        fee_total += money(item.unit_price * item.quantity * product.category.marketplace_commission_pct / Decimal(100))
        unit_cost = item.unit_cost
        if unit_cost is None:
            cost_total = None
        elif cost_total is not None:
            cost_total += money(unit_cost * item.quantity)
    assert policy is not None
    withdrawal = money((sale_total - fee_total) * policy.withdrawal_fee_pct / Decimal(100))
    entries = [
        (TransactionKind.SALE, sale_total, "Продажа"),
        (TransactionKind.MARKETPLACE_FEE, -fee_total, "Комиссия PlayerOK (по ставке категории)"),
        (TransactionKind.PAYMENT_FEE, -withdrawal, "Комиссия вывода (оценка по правилу цен)"),
    ]
    if cost_total is not None:
        entries.append((TransactionKind.PURCHASE, -cost_total, "Себестоимость"))
    for kind, amount, description in entries:
        stmt = (
            insert(Transaction)
            .values(
                kind=kind,
                order_id=order.id,
                amount=amount,
                currency="RUB",
                amount_rub=amount,
                description=description,
                dedupe_key=f"order:{order.id}:{kind.value}",
                is_test=order.is_test,
                occurred_at=order.completed_at or utcnow(),
            )
            .on_conflict_do_nothing(index_elements=[Transaction.dedupe_key])
        )
        await session.execute(stmt)
    order.marketplace_fee = money(fee_total)
    order.cost_total = cost_total
    order.net_profit = None if cost_total is None else money(sale_total - fee_total - withdrawal - cost_total)
    return order


async def mark_buyer_confirmed(session: AsyncSession, order: Order, actor: Actor) -> Order:
    if order.status not in (S.DELIVERED, S.DISPUTE):
        raise Conflict("Подтверждение покупателя возможно после выдачи")
    now = utcnow()
    order.buyer_confirmed_at = now
    order.completed_at = now
    await _move(session, order, S.COMPLETED, actor, "Покупатель подтвердил получение")
    await finalize(session, order)
    await audit(session, actor, "order.completed", entity_type="order", entity_id=order.id, details={"net_profit": str(order.net_profit)})
    profit = "не рассчитана — нет себестоимости" if order.net_profit is None else fmt_money(order.net_profit)
    await notify(
        session,
        "order_status",
        f"Сделка завершена: {order.number}{' 🧪' if order.is_test else ''}",
        f"Выручка: {fmt_money(order.total_amount)}\nКомиссия: {fmt_money(order.marketplace_fee)}\nЧистая прибыль: <b>{profit}</b>",
        severity=Severity.SUCCESS,
        buttons=order_buttons(order),
        entity_type="order",
        entity_id=order.id,
        dedupe_key=f"completed:{order.id}",
    )
    await hints.suggest(session, "buyer_confirm_text", "text", order, title=f"Сделка {order.number} завершена")
    active, cfg = await is_active(session, "review_reminder")
    if active:
        await jobs.enqueue(
            session,
            "order.reminder",
            {"order_id": order.id, "kind": "review", "n": 1},
            dedupe_key=f"reminder:review:{order.id}",
            run_after=now + timedelta(hours=int(cfg["delay_hours"])),
        )
    await _relist(session, order, actor)
    return order


async def _relist(session: AsyncSession, order: Order, actor: Actor) -> None:
    from . import listings

    for item in order.items:
        if item.listing_id is None:
            continue
        listing = await session.get(Listing, item.listing_id)
        if listing is not None and listing.relist_on_complete and listing.status is not None:
            await listings.after_sale(session, listing, actor)


async def refund(session: AsyncSession, order: Order, actor: Actor, reason: str) -> Order:
    if order.status in (S.REFUND, S.CANCELLED):
        raise Conflict("Заказ уже закрыт")
    for item in order.items:
        await inventory.release(session, item)
        await inventory.void_issued(session, item)
    if order.status is S.COMPLETED:
        await session.execute(
            insert(Transaction)
            .values(
                kind=TransactionKind.REFUND,
                order_id=order.id,
                amount=-order.total_amount,
                currency="RUB",
                amount_rub=-order.total_amount,
                description=f"Возврат: {reason[:200]}",
                dedupe_key=f"order:{order.id}:refund",
                is_test=order.is_test,
            )
            .on_conflict_do_nothing(index_elements=[Transaction.dedupe_key])
        )
    await _move(session, order, S.REFUND, actor, reason or "Возврат")
    await audit(session, actor, "order.refund", entity_type="order", entity_id=order.id, details={"reason": reason})
    return order


async def dispute(session: AsyncSession, order: Order, actor: Actor, reason: str) -> Order:
    await _move(session, order, S.DISPUTE, actor, reason or "Спор", force=order.status not in (S.REFUND, S.CANCELLED))
    order.automation_paused = True
    await audit(session, actor, "order.dispute", entity_type="order", entity_id=order.id, details={"reason": reason})
    await notify(
        session,
        "order_attention",
        f"Спор по заказу {order.number}",
        esc(reason or "Открыт спор"),
        severity=Severity.CRITICAL,
        buttons=order_buttons(order),
        entity_type="order",
        entity_id=order.id,
    )
    await hints.suggest(
        session, "problem_text", "text", order, title=f"Спор по заказу {order.number}", dedupe_key=f"problem:{order.id}:dispute"
    )
    return order


async def cancel(session: AsyncSession, order: Order, actor: Actor, reason: str) -> Order:
    if order.status in (S.DELIVERED, S.COMPLETED):
        raise Conflict("Выданный заказ нельзя отменить — оформите возврат")
    for item in order.items:
        await inventory.release(session, item)
    await _move(session, order, S.CANCELLED, actor, reason or "Отменён")
    await audit(session, actor, "order.cancel", entity_type="order", entity_id=order.id, details={"reason": reason})
    return order


async def set_status(session: AsyncSession, order: Order, status: OrderStatus, actor: Actor, reason: str) -> Order:
    """Manual intervention: any allowed transition with a reason."""
    if not reason.strip():
        raise DomainError("Укажите причину изменения статуса")
    special = {
        S.DELIVERED: mark_delivered,
        S.COMPLETED: mark_buyer_confirmed,
    }
    if status in special:
        return await special[status](session, order, actor)
    if status is S.REFUND:
        return await refund(session, order, actor, reason)
    if status is S.CANCELLED:
        return await cancel(session, order, actor, reason)
    if status is S.DISPUTE:
        return await dispute(session, order, actor, reason)
    await _move(session, order, status, actor, reason)
    await audit(session, actor, "order.status", entity_type="order", entity_id=order.id, details={"status": status.value, "reason": reason})
    return order


async def pause_automation(session: AsyncSession, order: Order, paused: bool, actor: Actor) -> Order:
    order.automation_paused = paused
    await _event(session, order, actor, "Автоматизация приостановлена" if paused else "Автоматизация возобновлена")
    await audit(session, actor, "order.automation", entity_type="order", entity_id=order.id, details={"paused": paused})
    return order


async def add_note(session: AsyncSession, order: Order, text: str, actor: Actor) -> Order:
    text = text.strip()[:1000]
    if not text:
        raise DomainError("Пустая заметка")
    order.notes = (order.notes + "\n" if order.notes else "") + f"[{actor.label}] {text}"
    await _event(session, order, actor, f"Заметка: {text}")
    return order


async def send_reminder(session: AsyncSession, order_id: int, kind: str, n: int) -> None:
    order = await get_order(session, order_id)
    if kind == "confirm":
        active, cfg = await is_active(session, "confirm_reminder")
        if not active or order.status is not S.DELIVERED or order.buyer_confirmed_at:
            return
        await hints.suggest(
            session,
            "confirm_reminder",
            "text",
            order,
            title=f"Напоминание о подтверждении #{n}: {order.number}",
            dedupe_key=f"rem:confirm:{order.id}:{n}",
        )
        order.reminders_sent = {**(order.reminders_sent or {}), "confirm": n}
        if n < int(cfg["max_count"]):
            await jobs.enqueue(
                session,
                "order.reminder",
                {"order_id": order.id, "kind": "confirm", "n": n + 1},
                dedupe_key=f"reminder:confirm:{order.id}:{n + 1}",
                run_after=utcnow() + timedelta(hours=int(cfg["interval_hours"])),
            )
    elif kind == "review":
        active, _ = await is_active(session, "review_reminder")
        if not active or order.status is not S.COMPLETED or order.review_received_at or (order.reminders_sent or {}).get("review"):
            return
        await hints.suggest(
            session, "review_reminder", "text", order, title=f"Просьба об отзыве: {order.number}", dedupe_key=f"rem:review:{order.id}"
        )
        order.reminders_sent = {**(order.reminders_sent or {}), "review": 1}


async def list_orders(
    session: AsyncSession,
    *,
    status: str | None = None,
    query: str = "",
    attention: bool = False,
    include_test: bool = True,
    page: int = 1,
    per_page: int = 10,
) -> tuple[list[Order], int]:
    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == OrderStatus(status))
    if attention:
        stmt = stmt.where(Order.needs_attention.is_(True))
    if not include_test:
        stmt = stmt.where(Order.is_test.is_(False))
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(Order.number.ilike(like), Order.external_id.ilike(like), Order.buyer_name.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(stmt.order_by(Order.id.desc()).offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return list(rows), total


def marketplace_note() -> str:
    market = get_marketplace()
    return market.reason("fetch_orders") if not market.supports("fetch_orders") else ""
