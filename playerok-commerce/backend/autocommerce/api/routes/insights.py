"""Research, analytics, pricing rules and the price calculator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...database.models import PriceRule
from ...services import analytics, exports, fx, repricing, research
from ...services.pricing import CostInput, PricingPolicy, calculate
from ...shared.timeutil import utcnow
from .. import serializers as ser
from ..deps import Context, need

router = APIRouter(tags=["insights"])


@router.get("/research")
async def ranking(include_excluded: bool = False, page: int = Query(1, ge=1), ctx: Context = Depends(need("view"))) -> dict:
    rows, total = await research.ranking(ctx.session, include_excluded=include_excluded, limit=25, offset=(page - 1) * 25)
    return {
        "items": [
            {
                "product": ser.product(p),
                "score": ser.d(s.total_score),
                "confidence": s.confidence.value,
                "factors": s.factors,
                "excluded_reason": s.excluded_reason,
                "computed_at": ser.dt(s.computed_at),
            }
            for p, s in rows
        ],
        "total": total,
        "page": page,
    }


@router.post("/research/recompute")
async def recompute(ctx: Context = Depends(need("view"))) -> dict:
    return {"products": await research.recompute_all(ctx.session)}


@router.get("/research/opportunities")
async def opportunities(q: str = Query("", max_length=100), page: int = Query(1, ge=1), ctx: Context = Depends(need("view"))) -> dict:
    items, total = await research.supplier_opportunities(ctx.session, limit=30, offset=(page - 1) * 30, search=q)
    return {"items": items, "total": total, "page": page}


def _period(period: str, date_from: date | None, date_to: date | None) -> analytics.Period:
    return analytics.period(period, date_from, date_to)


@router.get("/analytics")
async def get_analytics(
    period: str = "30d",
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    include_test: bool = False,
    ctx: Context = Depends(need("view")),
) -> dict:
    p = _period(period, date_from, date_to)
    return {
        "metrics": await analytics.metrics(ctx.session, p, include_test=include_test),
        "series": await analytics.timeseries(ctx.session, p, include_test=include_test),
        "breakdown": await analytics.breakdown(ctx.session, p, include_test=include_test),
        "sync": await analytics.sync_overview(ctx.session),
        "totals": await analytics.recorded_totals(ctx.session),
        "generated_at": utcnow().isoformat(),
    }


@router.get("/analytics/export")
async def export(
    fmt: Literal["csv", "xlsx"] = Query("xlsx", alias="format"),
    period: str = "30d",
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    include_test: bool = False,
    ctx: Context = Depends(need("analytics.export")),
) -> Response:
    data, name, media = await exports.analytics_export(ctx.session, _period(period, date_from, date_to), fmt, include_test)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/products-export")
async def products_export(
    fmt: Literal["csv", "xlsx"] = Query("xlsx", alias="format"), ctx: Context = Depends(need("analytics.export"))
) -> Response:
    data, name, media = await exports.products_export(ctx.session, fmt)
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/fx")
async def rates(ctx: Context = Depends(need("view"))) -> dict:
    return {"items": await fx.rates_overview(ctx.session), "source": "ЦБ РФ (cbr.ru/scripts/XML_daily.asp)"}


@router.post("/fx/sync")
async def sync_rates(ctx: Context = Depends(need("pricing.manage"))) -> dict:
    run = await fx.sync_cbr(ctx.session)
    return {"run": ser.sync_run(run), "items": await fx.rates_overview(ctx.session)}


@router.get("/pricing/rules")
async def rules(ctx: Context = Depends(need("view"))) -> dict:
    rows = (await ctx.session.execute(select(PriceRule).order_by(PriceRule.scope, PriceRule.id))).scalars().all()
    glob = await repricing.global_policy(ctx.session)
    return {
        "global": glob.to_values(),
        "defaults": PricingPolicy().to_values(),
        "overrides": [
            {"id": r.id, "scope": r.scope, "category_id": r.category_id, "product_id": r.product_id, "values": r.values}
            for r in rows
            if r.scope != "global"
        ],
        "fields": list(PricingPolicy.FIELDS),
    }


class RuleIn(BaseModel):
    values: dict[str, str | int | None]


@router.put("/pricing/rules/global")
async def save_global(body: RuleIn, ctx: Context = Depends(need("pricing.manage"))) -> dict:
    await repricing.save_rule(ctx.session, "global", body.values, ctx.actor)
    from ...services import jobs

    await jobs.enqueue(ctx.session, "products.reprice_all", {}, dedupe_key="reprice_all")
    return {"global": (await repricing.global_policy(ctx.session)).to_values()}


@router.put("/pricing/rules/{scope}/{ref_id}")
async def save_scoped(
    scope: Literal["category", "product"], ref_id: int, body: RuleIn, ctx: Context = Depends(need("pricing.manage"))
) -> dict:
    rule = await repricing.save_rule(
        ctx.session,
        scope,
        body.values,
        ctx.actor,
        category_id=ref_id if scope == "category" else None,
        product_id=ref_id if scope == "product" else None,
    )
    from ...services import jobs

    await jobs.enqueue(ctx.session, "products.reprice_all", {}, dedupe_key="reprice_all")
    return {"id": rule.id, "values": rule.values}


@router.delete("/pricing/rules/{rule_id}")
async def delete_rule(rule_id: int, ctx: Context = Depends(need("pricing.manage"))) -> dict:
    rule = await ctx.session.get(PriceRule, rule_id)
    if rule is not None and rule.scope != "global":
        await ctx.session.delete(rule)
    return {"ok": True}


class CalcIn(BaseModel):
    purchase_price: Decimal = Field(gt=0)
    currency: str = Field(default="RUB", max_length=8)
    marketplace_commission_pct: Decimal = Field(default=Decimal("20"), ge=0, lt=100)
    supplier_fee_pct: Decimal = Field(default=Decimal("0"), ge=0, lt=100)
    sale_price: Decimal | None = Field(default=None, gt=0)
    competitor_min: Decimal | None = Field(default=None, gt=0)
    overrides: dict[str, str | int | None] = Field(default_factory=dict)


@router.post("/pricing/calculate")
async def calculator(body: CalcIn, ctx: Context = Depends(need("view"))) -> dict:
    from ...services.pricing import MarketInput

    policy = PricingPolicy.from_values(body.overrides, base=await repricing.global_policy(ctx.session))
    rate = await fx.latest_rate(ctx.session, body.currency)
    result = calculate(
        CostInput(
            purchase_price=body.purchase_price,
            purchase_currency=body.currency.upper(),
            fx_rate=rate[0] if rate else None,
            supplier_fee_pct=body.supplier_fee_pct,
            marketplace_commission_pct=body.marketplace_commission_pct,
            price_captured_at=utcnow(),
        ),
        policy,
        current_price=body.sale_price,
        market=MarketInput(body.competitor_min, None, None, utcnow()) if body.competitor_min else None,
    )
    return {
        "result": result.as_dict(),
        "fx_rate": ser.d(rate[0]) if rate else None,
        "fx_date": ser.dt(rate[1]) if rate and rate[1] else None,
    }
