from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ...services import catalog, listings
from ...services.auth import require
from .. import serializers as ser
from ..deps import Context, need

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("")
async def list_listings(
    status: str | None = None,
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    ctx: Context = Depends(need("view")),
) -> dict:
    rows, total = await listings.search(ctx.session, status=status, query=q, page=page, per_page=per_page)
    return {"items": [ser.listing(x) for x in rows], "total": total, "page": page, "per_page": per_page}


@router.get("/export.csv")
async def export(status: str | None = None, ctx: Context = Depends(need("view"))) -> Response:
    rows, _ = await listings.search(ctx.session, status=status, per_page=1000)
    return Response(
        listings.export_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="listings.csv"'},
    )


class CreateIn(BaseModel):
    product_id: int
    price_strategy: Literal["recommended", "target", "min"] = "recommended"


@router.post("")
async def create(body: CreateIn, ctx: Context = Depends(need("listings.manage"))) -> dict:
    product = await catalog.get_product(ctx.session, body.product_id)
    listing = await listings.create(ctx.session, product, ctx.actor, price_strategy=body.price_strategy)
    return ser.listing(listing)


async def _detail(ctx: Context, listing_id: int) -> dict[str, Any]:
    listing = await listings.get_listing(ctx.session, listing_id)
    images = await listings.images(ctx.session, listing_id)
    history = await listings.history(ctx.session, listing_id)
    return {
        **ser.listing(listing),
        "export": listings.export_payload(listing, f"/api/v1/images/{images[0].id}/file" if images else None),
        "images": [
            {"id": i.id, "template": i.template_code, "version": i.listing_version, "url": f"/api/v1/images/{i.id}/file"} for i in images
        ],
        "history": [
            {"version": h.version, "action": h.action, "actor": h.actor, "at": ser.dt(h.created_at), "snapshot": h.snapshot}
            for h in history
        ],
    }


@router.get("/{listing_id}")
async def detail(listing_id: int, ctx: Context = Depends(need("view"))) -> dict:
    return await _detail(ctx, listing_id)


class UpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal | None = Field(default=None, gt=0, le=10_000_000)
    quantity: int | None = Field(default=None, ge=1, le=100_000)
    marketplace_category: str | None = Field(default=None, max_length=200)
    relist_on_complete: bool | None = None


@router.patch("/{listing_id}")
async def update(listing_id: int, body: UpdateIn, ctx: Context = Depends(need("listings.manage"))) -> dict:
    if body.price is not None:
        require(ctx.actor, "pricing.manage")
    listing = await listings.get_listing(ctx.session, listing_id, lock=True)
    await listings.update(ctx.session, listing, body.model_dump(exclude_none=True), ctx.actor)
    return await _detail(ctx, listing_id)


@router.post("/{listing_id}/prepare")
async def prepare(listing_id: int, ctx: Context = Depends(need("listings.manage"))) -> dict:
    listing = await listings.get_listing(ctx.session, listing_id, lock=True)
    await listings.prepare(ctx.session, listing, ctx.actor)
    return await _detail(ctx, listing_id)


@router.post("/{listing_id}/confirm-preview")
async def confirm_preview(listing_id: int, ctx: Context = Depends(need("listings.publish"))) -> dict:
    listing = await listings.get_listing(ctx.session, listing_id, lock=True)
    await listings.confirm_preview(ctx.session, listing, ctx.actor)
    return await _detail(ctx, listing_id)


@router.post("/{listing_id}/publish")
async def publish(listing_id: int, ctx: Context = Depends(need("listings.publish"))) -> dict:
    listing = await listings.get_listing(ctx.session, listing_id, lock=True)
    result = await listings.publish(ctx.session, listing, ctx.actor)
    return {"result": result, "listing": await _detail(ctx, listing_id)}


class PublishedIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    url: str | None = Field(default=None, max_length=500)


@router.post("/{listing_id}/mark-published")
async def mark_published(listing_id: int, body: PublishedIn, ctx: Context = Depends(need("listings.publish"))) -> dict:
    listing = await listings.get_listing(ctx.session, listing_id, lock=True)
    result = await listings.mark_published(ctx.session, listing, body.external_id, body.url, ctx.actor)
    return {"result": result, "listing": await _detail(ctx, listing_id)}


class StateIn(BaseModel):
    reason: str = Field(default="", max_length=500)


@router.post("/{listing_id}/{action}")
async def state(
    listing_id: int, action: Literal["pause", "resume", "archive"], body: StateIn, ctx: Context = Depends(need("listings.manage"))
) -> dict:
    listing = await listings.get_listing(ctx.session, listing_id, lock=True)
    await listings.set_state(ctx.session, listing, action, ctx.actor, body.reason)
    return await _detail(ctx, listing_id)


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    action: Literal["prepare", "publish", "pause", "resume", "archive", "price_change_pct", "set_quantity"]
    confirm: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


@router.post("/bulk")
async def bulk(body: BulkIn, ctx: Context = Depends(need("listings.manage"))) -> dict:
    if body.action == "publish":
        require(ctx.actor, "listings.publish")
    if body.action == "price_change_pct":
        require(ctx.actor, "pricing.manage")
    return await listings.bulk(ctx.session, body.ids, body.action, ctx.actor, confirm=body.confirm, data=body.data)
