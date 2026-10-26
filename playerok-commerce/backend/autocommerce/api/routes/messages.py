from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...database.enums import MessageStatus
from ...database.models import AutoresponderRule, Review
from ...integrations.marketplace.base import CAPABILITY_LABELS
from ...integrations.marketplace.playerok_manual import get_marketplace
from ...services import messages, orders
from ...services.audit import audit
from ...shared.errors import NotFound
from .. import serializers as ser
from ..deps import Context, need

router = APIRouter(tags=["messages"])


def integration() -> dict:
    market = get_marketplace()
    return {
        "adapter": market.code,
        "title": market.title,
        "capabilities": {
            name: {"label": label, "available": market.supports(name), "reason": "" if market.supports(name) else market.reason(name)}
            for name, label in CAPABILITY_LABELS.items()
        },
    }


@router.get("/marketplace")
async def marketplace(ctx: Context = Depends(need("view"))) -> dict:
    return integration()


@router.get("/messages")
async def list_messages(
    status: str | None = None,
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    ctx: Context = Depends(need("view")),
) -> dict:
    rows, total = await messages.list_messages(ctx.session, status=status, page=page, per_page=per_page, query=q)
    return {"items": [ser.message(m) for m in rows], "total": total, "page": page, "per_page": per_page, "integration": integration()}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    buyer_name: str | None = Field(default=None, max_length=120)
    order_ref: str | None = Field(default=None, max_length=120)


async def _order(ctx: Context, ref: str | None):
    if not ref:
        return None
    order = await orders.find_order(ctx.session, ref)
    if order is None:
        raise NotFound(f"Заказ «{ref}» не найден")
    return order


@router.post("/messages")
async def record(body: MessageIn, ctx: Context = Depends(need("messages.manage"))) -> dict:
    order = await _order(ctx, body.order_ref)
    message = await messages.record_incoming(ctx.session, text=body.text, buyer_name=body.buyer_name, order=order, actor=ctx.actor)
    return ser.message(message)


class StatusIn(BaseModel):
    status: MessageStatus


@router.post("/messages/{message_id}/status")
async def set_status(message_id: int, body: StatusIn, ctx: Context = Depends(need("messages.manage"))) -> dict:
    return ser.message(await messages.set_status(ctx.session, message_id, body.status, ctx.actor))


class TestIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    order_ref: str | None = Field(default=None, max_length=120)


@router.post("/autoresponder/test")
async def test_rules(body: TestIn, ctx: Context = Depends(need("view"))) -> dict:
    return await messages.test_rules(ctx.session, body.text, await _order(ctx, body.order_ref))


def rule_out(r: AutoresponderRule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "priority": r.priority,
        "enabled": r.enabled,
        "match_type": r.match_type,
        "patterns": r.patterns,
        "order_statuses": r.order_statuses,
        "action": r.action,
        "reply_template": r.reply_template,
        "hits": r.hits,
        "last_hit_at": ser.dt(r.last_hit_at),
    }


@router.get("/autoresponder/rules")
async def rules(ctx: Context = Depends(need("view"))) -> dict:
    rows = (await ctx.session.execute(select(AutoresponderRule).order_by(AutoresponderRule.priority, AutoresponderRule.id))).scalars()
    return {"items": [rule_out(r) for r in rows]}


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    priority: int = Field(default=100, ge=0, le=10_000)
    enabled: bool = True
    match_type: str = "keywords"
    patterns: list[str] = Field(min_length=1, max_length=50)
    order_statuses: list[str] = Field(default_factory=list)
    action: str = "reply"
    reply_template: str = Field(default="", max_length=2000)


@router.post("/autoresponder/rules")
async def create_rule(body: RuleIn, ctx: Context = Depends(need("autosettings.manage"))) -> dict:
    rule = AutoresponderRule(**messages.validate_rule(body.model_dump()))
    ctx.session.add(rule)
    await ctx.session.flush()
    await audit(ctx.session, ctx.actor, "autoresponder.rule_create", entity_type="rule", entity_id=rule.id)
    return rule_out(rule)


@router.put("/autoresponder/rules/{rule_id}")
async def update_rule(rule_id: int, body: RuleIn, ctx: Context = Depends(need("autosettings.manage"))) -> dict:
    rule = await ctx.session.get(AutoresponderRule, rule_id)
    if rule is None:
        raise NotFound("Правило не найдено")
    for key, value in messages.validate_rule(body.model_dump()).items():
        setattr(rule, key, value)
    await audit(ctx.session, ctx.actor, "autoresponder.rule_update", entity_type="rule", entity_id=rule.id)
    return rule_out(rule)


@router.delete("/autoresponder/rules/{rule_id}")
async def delete_rule(rule_id: int, ctx: Context = Depends(need("autosettings.manage"))) -> dict:
    rule = await ctx.session.get(AutoresponderRule, rule_id)
    if rule is None:
        raise NotFound("Правило не найдено")
    await ctx.session.delete(rule)
    await audit(ctx.session, ctx.actor, "autoresponder.rule_delete", entity_type="rule", entity_id=rule_id)
    return {"ok": True}


@router.get("/reviews")
async def list_reviews(page: int = Query(1, ge=1), ctx: Context = Depends(need("view"))) -> dict:
    rows = (await ctx.session.execute(select(Review).order_by(Review.id.desc()).offset((page - 1) * 50).limit(50))).scalars()
    return {"items": [ser.review(r) for r in rows]}


class ReviewIn(BaseModel):
    order_ref: str | None = Field(default=None, max_length=120)
    rating: int | None = Field(default=None, ge=1, le=5)
    text: str = Field(default="", max_length=4000)


@router.post("/reviews")
async def record_review(body: ReviewIn, ctx: Context = Depends(need("messages.manage"))) -> dict:
    review = await messages.record_review(
        ctx.session, order=await _order(ctx, body.order_ref), rating=body.rating, text=body.text, actor=ctx.actor
    )
    return ser.review(review)
