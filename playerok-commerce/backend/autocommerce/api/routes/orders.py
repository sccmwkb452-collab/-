from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...database.enums import OrderStatus
from ...database.models import CustomerMessage, OrderEvent, Review
from ...services import inventory, orders, suppliers
from ...services.auth import require
from ...shared.errors import DomainError
from .. import serializers as ser
from ..deps import Context, need

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
async def list_orders(
    status: str | None = None,
    q: str = Query("", max_length=100),
    attention: bool = False,
    include_test: bool = True,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    ctx: Context = Depends(need("view")),
) -> dict:
    rows, total = await orders.list_orders(
        ctx.session, status=status, query=q, attention=attention, include_test=include_test, page=page, per_page=per_page
    )
    return {
        "items": [ser.order(o) for o in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "marketplace_note": orders.marketplace_note(),
    }


class ItemIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=10_000)
    unit_price: Decimal = Field(gt=0, le=10_000_000)


class OrderIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    buyer_name: str | None = Field(default=None, max_length=120)
    buyer_link: str | None = Field(default=None, max_length=500)
    items: list[ItemIn] = Field(min_length=1, max_length=20)
    notes: str = Field(default="", max_length=2000)
    is_test: bool | None = None


@router.post("")
async def create(body: OrderIn, ctx: Context = Depends(need("orders.manage"))) -> dict:
    order, created = await orders.create_order(
        ctx.session,
        orders.NewOrder(
            external_id=body.external_id,
            items=[orders.NewItem(i.product_id, i.quantity, i.unit_price) for i in body.items],
            buyer_name=body.buyer_name,
            buyer_data={"link": body.buyer_link or ""},
            notes=body.notes,
            is_test=body.is_test,
        ),
        ctx.actor,
    )
    return {"order": ser.order(order), "created": created}


@router.post("/import")
async def import_orders(file: UploadFile = File(...), ctx: Context = Depends(need("orders.manage"))) -> dict:
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise DomainError("Файл больше 2 МБ")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    return await orders.import_csv(ctx.session, text, ctx.actor)


@router.get("/{order_id}")
async def detail(order_id: int, ctx: Context = Depends(need("view"))) -> dict:
    order = await orders.get_order(ctx.session, order_id)
    events = (await ctx.session.execute(select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id.desc()))).scalars()
    msgs = (
        await ctx.session.execute(
            select(CustomerMessage).where(CustomerMessage.order_id == order.id).order_by(CustomerMessage.id.desc()).limit(50)
        )
    ).scalars()
    reviews = (await ctx.session.execute(select(Review).where(Review.order_id == order.id))).scalars()
    items = []
    for item in order.items:
        so = await suppliers.latest_for_item(ctx.session, item.id)
        items.append(
            {
                "item_id": item.id,
                "codes": [ser.code(c) for c in await inventory.assigned(ctx.session, item.id)],
                "supplier_order": ser.supplier_order(so) if so else None,
            }
        )
    return {
        "order": ser.order(order, detailed=True),
        "fulfilment": items,
        "events": [
            {"at": ser.dt(e.created_at), "from": e.from_status, "to": e.to_status, "actor": e.actor, "message": e.message} for e in events
        ],
        "messages": [ser.message(m) for m in msgs],
        "reviews": [ser.review(r) for r in reviews],
        "transitions": sorted(s.value for s in orders.TRANSITIONS[order.status]),
    }


Action = Literal[
    "continue",
    "retry",
    "confirm_purchase",
    "manual_purchase",
    "mark_purchased",
    "delivered",
    "buyer_confirmed",
    "refund",
    "dispute",
    "cancel",
    "pause",
    "resume",
    "note",
    "status",
]


class ActionIn(BaseModel):
    action: Action
    reason: str = Field(default="", max_length=1000)
    cost_rub: Decimal | None = Field(default=None, ge=0)
    status: OrderStatus | None = None


PERMISSIONS = {"confirm_purchase": "suppliers.purchase", "mark_purchased": "orders.manage"}


@router.post("/{order_id}/action")
async def action(order_id: int, body: ActionIn, ctx: Context = Depends(need("orders.manage"))) -> dict:
    require(ctx.actor, PERMISSIONS.get(body.action, "orders.manage"))
    order = await orders.get_order(ctx.session, order_id, lock=True)
    a, s, actor = body.action, ctx.session, ctx.actor
    if a == "continue":
        await orders.continue_after_review(s, order, actor)
    elif a == "retry":
        await orders.retry(s, order, actor)
    elif a == "confirm_purchase":
        await orders.confirm_purchase(s, order, actor)
    elif a == "manual_purchase":
        await orders.choose_manual_purchase(s, order, actor)
    elif a == "mark_purchased":
        await orders.mark_purchased(s, order, actor, cost_rub=body.cost_rub)
    elif a == "delivered":
        await orders.mark_delivered(s, order, actor)
    elif a == "buyer_confirmed":
        await orders.mark_buyer_confirmed(s, order, actor)
    elif a == "refund":
        await orders.refund(s, order, actor, body.reason)
    elif a == "dispute":
        await orders.dispute(s, order, actor, body.reason)
    elif a == "cancel":
        await orders.cancel(s, order, actor, body.reason)
    elif a in ("pause", "resume"):
        await orders.pause_automation(s, order, a == "pause", actor)
    elif a == "note":
        await orders.add_note(s, order, body.reason, actor)
    elif a == "status":
        if body.status is None:
            raise DomainError("Укажите статус")
        await orders.set_status(s, order, body.status, actor, body.reason)
    order = await orders.get_order(s, order_id)
    return {"order": ser.order(order, detailed=True)}


class AddCodesIn(BaseModel):
    item_id: int
    codes: list[str] = Field(min_length=1, max_length=100)
    unit_cost: Decimal | None = Field(default=None, ge=0)


@router.post("/{order_id}/codes")
async def add_codes(order_id: int, body: AddCodesIn, ctx: Context = Depends(need("inventory.manage"))) -> dict:
    order = await orders.get_order(ctx.session, order_id, lock=True)
    result = await orders.add_codes(ctx.session, order, body.item_id, body.codes, ctx.actor, unit_cost=body.unit_cost)
    order = await orders.get_order(ctx.session, order_id)
    return {"result": result, "order": ser.order(order, detailed=True)}
