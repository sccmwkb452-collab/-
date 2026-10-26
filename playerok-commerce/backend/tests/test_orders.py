"""Order Manager: idempotency, no double purchase, no double issue of codes,
supplier errors, guards, finances, refunds, CSV import."""

from __future__ import annotations

import asyncio
from decimal import Decimal as D

import httpx
import pytest
from sqlalchemy import func, select

from autocommerce.database.enums import CodeStatus, DeliveryType, OrderStatus, PurchaseMode, SupplierOrderStatus, TransactionKind
from autocommerce.database.models import AutomationJob, DigitalCode, Order, SupplierOrder, Transaction
from autocommerce.database.session import get_sessionmaker, session_scope
from autocommerce.integrations.suppliers import registry
from autocommerce.integrations.suppliers.base import CatalogItem, ConnectionCheck, PurchaseResult, SupplierAdapter, SupplierCapabilities
from autocommerce.services import app_settings, inventory, orders
from autocommerce.services.audit import CLI
from autocommerce.shared.errors import Blocked, Conflict

from .factories import add_fx, link, make_product, make_supplier_item

pytestmark = pytest.mark.usefixtures("seeded")


class FakeSupplier(SupplierAdapter):
    code = "fake"
    title = "Fake"
    capabilities = SupplierCapabilities(price_list=True, balance=True, purchase=True, order_status=True, returns_codes=True)

    def __init__(self, result: PurchaseResult | Exception) -> None:
        super().__init__({"k": "v"})
        self.result = result
        self.calls = 0

    def configured(self) -> bool:
        return True

    async def check(self) -> ConnectionCheck:
        return ConnectionCheck(True, "ok", D("1000"), "USD")

    async def fetch_catalog(self) -> list[CatalogItem]:
        return []

    async def purchase(self, request):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return PurchaseResult(
            self.result.status,
            self.result.external_id,
            self.result.cost,
            self.result.currency,
            list(self.result.codes),
            self.result.message,
        )


async def new_order(product_id: int, external_id: str = "deal-1", price: str = "1500", qty: int = 1, **kw) -> int:
    async with session_scope() as s:
        order, _ = await orders.create_order(
            s, orders.NewOrder(external_id=external_id, items=[orders.NewItem(product_id, qty, D(price))], **kw), CLI, process=False
        )
        return order.id


async def process(order_id: int, **kw) -> Order:
    async with session_scope() as s:
        return await orders.process(s, order_id, **kw)


async def load(order_id: int) -> Order:
    async with get_sessionmaker()() as s:
        return await orders.get_order(s, order_id)


async def go_live() -> None:
    async with session_scope() as s:
        await app_settings.set_setting(s, "operations.mode", "live", CLI)


async def test_same_deal_is_created_once():
    pid = await make_product()
    async with session_scope() as s:
        first, created1 = await orders.create_order(s, orders.NewOrder("deal-42", [orders.NewItem(pid, 1, D("1500"))]), CLI)
        second, created2 = await orders.create_order(s, orders.NewOrder("deal-42", [orders.NewItem(pid, 1, D("1500"))]), CLI)
    assert created1 and not created2 and first.id == second.id
    async with get_sessionmaker()() as s:
        assert (await s.execute(select(func.count(Order.id)))).scalar_one() == 1
        jobs = (await s.execute(select(func.count()).where(AutomationJob.kind == "order.process"))).scalar_one()
        assert jobs == 1
    assert first.number == "PO-000001"


async def test_code_from_stock_is_reserved_and_issued_once():
    pid = await make_product()
    async with session_scope() as s:
        product = await orders.get_product(s, pid)
        await inventory.add_codes(s, product, ["AAAA-1111-BBBB"], CLI, unit_cost=D("900"), is_test=True)
    o1 = await new_order(pid, "d1", is_test=True)
    o2 = await new_order(pid, "d2", is_test=True)
    order1 = await process(o1)
    order2 = await process(o2)
    assert order1.status is OrderStatus.READY_FOR_DELIVERY
    assert order2.status is OrderStatus.PENDING_PURCHASE  # no second code: the same code is never given twice
    async with session_scope() as s:
        order = await orders.get_order(s, o1, lock=True)
        await orders.mark_delivered(s, order, CLI)
    async with get_sessionmaker()() as s:
        code = (await s.execute(select(DigitalCode))).scalar_one()
        assert code.status is CodeStatus.ISSUED and code.order_item_id == order1.items[0].id
    # processing again changes nothing
    again = await process(o1)
    assert again.status is OrderStatus.DELIVERED


async def test_duplicate_code_import_is_rejected():
    pid = await make_product()
    async with session_scope() as s:
        product = await orders.get_product(s, pid)
        r1 = await inventory.add_codes(s, product, ["KEY-12345", "key-12345 "], CLI)
        r2 = await inventory.add_codes(s, product, ["KEY-12345"], CLI)
    assert (r1.added, r1.duplicates) == (1, 1)  # same code with other case/spaces
    assert (r2.added, r2.duplicates) == (0, 1)


async def test_parallel_reservation_never_shares_a_code():
    pid = await make_product()
    async with session_scope() as s:
        product = await orders.get_product(s, pid)
        await inventory.add_codes(s, product, [f"CODE-{i:04d}" for i in range(5)], CLI, is_test=True)
    ids = [await new_order(pid, f"p{i}", is_test=True) for i in range(5)]
    results = await asyncio.gather(*(process(i) for i in ids))
    assert all(r.status is OrderStatus.READY_FOR_DELIVERY for r in results)
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(DigitalCode.order_item_id).where(DigitalCode.status == CodeStatus.RESERVED))).scalars().all()
    assert len(rows) == 5 and len(set(rows)) == 5


async def test_manual_supplier_requires_manual_purchase_then_profit_is_fixed(sender):
    pid = await make_product(name="Telegram Stars 1000", category="tg_stars", delivery=DeliveryType.MANUAL, manual_cost=None)
    await add_fx("USD", "80")
    sp = await make_supplier_item("fragment", external_id="stars:1000", price="15", mode=PurchaseMode.MANUAL)
    await link(pid, sp)
    oid = await new_order(pid, "frag-1", price="1700", buyer_data={"link": "@buyer"})
    order = await process(oid)
    assert order.status is OrderStatus.PENDING_PURCHASE and "ручн" in order.status_reason.lower()
    async with session_scope() as s:
        order = await orders.get_order(s, oid, lock=True)
        await orders.mark_purchased(s, order, CLI, cost_rub=D("1250"))
    async with session_scope() as s:
        order = await orders.get_order(s, oid, lock=True)
        assert order.status is OrderStatus.READY_FOR_DELIVERY
        await orders.mark_delivered(s, order, CLI)
        await orders.mark_buyer_confirmed(s, order, CLI)
    async with session_scope() as s:
        order = await orders.get_order(s, oid, lock=True)
        assert order.status is OrderStatus.COMPLETED
        # sale 1700 − 10 % fee 170 − withdrawal 3 % of 1530 = 45.90 − cost 1250
        assert order.net_profit == D("1700") - D("170") - D("45.90") - D("1250")
        await orders.finalize(s, order)  # idempotent
    async with get_sessionmaker()() as s:
        kinds = (await s.execute(select(Transaction.kind, func.count()).group_by(Transaction.kind))).all()
    assert dict(kinds) == {
        TransactionKind.SALE: 1,
        TransactionKind.MARKETPLACE_FEE: 1,
        TransactionKind.PAYMENT_FEE: 1,
        TransactionKind.PURCHASE: 1,
    }


async def test_confirm_mode_waits_for_owner_and_purchase_is_not_repeated(sender):
    await add_fx("USD", "80")
    pid = await make_product(manual_cost=None)
    sp = await make_supplier_item("reloadly", external_id="5:10", price="10", mode=PurchaseMode.CONFIRM)
    await link(pid, sp)
    fake = FakeSupplier(PurchaseResult(SupplierOrderStatus.SUCCEEDED, "tx-1", D("10"), "USD", ["REAL-CODE-0001"]))
    registry.override("reloadly", fake)
    await go_live()
    oid = await new_order(pid, "rl-1", price="1500", is_test=False)
    order = await process(oid)
    assert order.status is OrderStatus.PENDING_CONFIRMATION and fake.calls == 0
    async with session_scope() as s:
        order = await orders.get_order(s, oid, lock=True)
        await orders.confirm_purchase(s, order, CLI)
    order = await load(oid)
    assert order.status is OrderStatus.READY_FOR_DELIVERY and fake.calls == 1
    # repeated processing / confirmation must not buy again
    async with session_scope() as s:
        order = await orders.get_order(s, oid, lock=True)
        await orders.process(s, oid, CLI, confirmed=True)
    assert fake.calls == 1
    async with get_sessionmaker()() as s:
        assert (await s.execute(select(func.count(SupplierOrder.id)))).scalar_one() == 1
        code = (await s.execute(select(DigitalCode))).scalar_one()
        assert code.code_enc != "REAL-CODE-0001" and "REAL" not in code.code_mask  # stored encrypted, only a mask is visible


async def test_supplier_error_moves_order_to_error_and_notifies(sender):
    await add_fx("USD", "80")
    pid = await make_product(manual_cost=None)
    sp = await make_supplier_item("reloadly", external_id="5:10", price="10", mode=PurchaseMode.CONFIRM)
    await link(pid, sp)
    registry.override("reloadly", FakeSupplier(PurchaseResult(SupplierOrderStatus.FAILED, message="out of stock")))
    await go_live()
    oid = await new_order(pid, "rl-err", price="1500", is_test=False)
    order = await process(oid, actor=CLI, confirmed=True)
    assert order.status is OrderStatus.ERROR and "out of stock" in order.status_reason
    async with get_sessionmaker()() as s:
        from autocommerce.database.models import Notification

        titles = (await s.execute(select(Notification.title))).scalars().all()
    assert any("ошибка" in t for t in titles)


async def test_unknown_purchase_outcome_blocks_retry(sender):
    await add_fx("USD", "80")
    pid = await make_product(manual_cost=None)
    sp = await make_supplier_item("reloadly", external_id="5:10", price="10", mode=PurchaseMode.CONFIRM)
    await link(pid, sp)
    fake = FakeSupplier(httpx.ReadTimeout("lost"))
    registry.override("reloadly", fake)
    await go_live()
    oid = await new_order(pid, "rl-unk", price="1500", is_test=False)
    order = await process(oid, actor=CLI, confirmed=True)
    assert order.status is OrderStatus.PENDING_REVIEW and "неизвестен" in order.status_reason
    async with session_scope() as s:
        order = await orders.get_order(s, oid, lock=True)
        with pytest.raises(Blocked):
            from autocommerce.services import suppliers

            await suppliers.purchase_for_item(s, order, order.items[0], CLI, confirmed=True)
    assert fake.calls == 1


async def test_kill_switch_stops_processing():
    pid = await make_product()
    oid = await new_order(pid, "ks-1")
    async with session_scope() as s:
        await app_settings.set_kill_switch(s, True, CLI, "test")
    order = await process(oid)
    assert order.status is OrderStatus.NEW


async def test_limits_block_purchase(sender):
    await add_fx("USD", "80")
    pid = await make_product(manual_cost=None)
    sp = await make_supplier_item("reloadly", external_id="5:10", price="10", mode=PurchaseMode.CONFIRM)
    await link(pid, sp)
    async with session_scope() as s:
        from autocommerce.services import suppliers

        supplier = await suppliers.get_supplier(s, "reloadly")
        supplier.max_single_purchase = D("100")
    registry.override("reloadly", FakeSupplier(PurchaseResult(SupplierOrderStatus.SUCCEEDED, "x", D("10"), "USD", ["C-1"])))
    await go_live()
    oid = await new_order(pid, "lim-1", price="1500", is_test=False)
    order = await process(oid, actor=CLI, confirmed=True)
    assert order.status is OrderStatus.PENDING_REVIEW and "лимит" in order.status_reason.lower()


async def test_sale_below_minimum_goes_to_review():
    pid = await make_product(manual_cost="1000")
    oid = await new_order(pid, "cheap", price="500")
    order = await process(oid)
    assert order.status is OrderStatus.PENDING_REVIEW and "ниже минимальной" in order.status_reason


async def test_refund_voids_issued_codes_and_cancel_releases_reserved():
    pid = await make_product()
    async with session_scope() as s:
        product = await orders.get_product(s, pid)
        await inventory.add_codes(s, product, ["R-1111", "R-2222"], CLI, is_test=True)
    o1 = await new_order(pid, "r1", is_test=True)
    o2 = await new_order(pid, "r2", is_test=True)
    await process(o1)
    await process(o2)
    async with session_scope() as s:
        order = await orders.get_order(s, o1, lock=True)
        await orders.mark_delivered(s, order, CLI)
        await orders.refund(s, order, CLI, "не подошёл регион")
        order2 = await orders.get_order(s, o2, lock=True)
        await orders.cancel(s, order2, CLI, "покупатель отказался")
    async with get_sessionmaker()() as s:
        statuses = dict((await s.execute(select(DigitalCode.code_mask, DigitalCode.status))).all())
    assert sorted(statuses.values(), key=str) == sorted([CodeStatus.VOID, CodeStatus.AVAILABLE], key=str)


async def test_invalid_transitions_are_refused():
    pid = await make_product()
    oid = await new_order(pid, "t1")
    async with session_scope() as s:
        order = await orders.get_order(s, oid, lock=True)
        with pytest.raises(Conflict):
            await orders.mark_buyer_confirmed(s, order, CLI)


async def test_csv_import_is_idempotent():
    pid = await make_product(name="Steam Wallet 10 USD")
    async with get_sessionmaker()() as s:
        sku = (await orders.get_product(s, pid)).sku
    csv_text = f"external_id;placed_at;sku;quantity;unit_price;buyer;status;unit_cost\nA-1;20.10.2026 12:00;{sku};1;1500;ivan;completed;1000\nA-2;21.10.2026;{sku};1;1600;petr;new;\nA-3;;missing-sku;1;100;x;new;\n"
    async with session_scope() as s:
        first = await orders.import_csv(s, csv_text, CLI)
    async with session_scope() as s:
        second = await orders.import_csv(s, csv_text, CLI)
    assert (first["created"], first["errors"]) == (2, 1)
    assert second["created"] == 0 and second["duplicates"] == 2
    async with get_sessionmaker()() as s:
        done = (await s.execute(select(Order).where(Order.external_id == "A-1"))).scalar_one()
    assert done.status is OrderStatus.COMPLETED and done.net_profit is not None
