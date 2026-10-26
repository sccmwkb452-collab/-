"""Model → JSON. Money as strings (exact), dates in ISO 8601, no secrets."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from ..database.enums import (
    COMPLIANCE_LABELS,
    LISTING_STATUS_LABELS,
    ORDER_STATUS_LABELS,
    PURCHASE_MODE_LABELS,
    SUPPLIER_STATUS_LABELS,
)
from ..database.models import (
    AuditLog,
    AutomationLog,
    CustomerMessage,
    DigitalCode,
    Listing,
    MarketPriceSnapshot,
    Notification,
    Order,
    Product,
    ProductCategory,
    Review,
    Supplier,
    SupplierOrder,
    SupplierProduct,
    SyncRun,
    User,
)
from ..integrations.suppliers import registry
from ..services.catalog import compliance_of
from ..services.pricing import STATUS_LABELS as PRICING_LABELS


def d(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def dt(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def user(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name,
        "role": u.role.code.value,
        "role_name": u.role.name,
        "permissions": u.role.permissions,
        "telegram_linked": u.telegram_id is not None,
        "is_active": u.is_active,
        "totp_enabled": u.totp_enabled,
        "last_login_at": dt(u.last_login_at),
        "created_at": dt(u.created_at),
    }


def category(c: ProductCategory) -> dict[str, Any]:
    return {
        "id": c.id,
        "code": c.code,
        "name": c.name,
        "group": c.group,
        "marketplace_commission_pct": d(c.marketplace_commission_pct),
        "commission_source": c.commission_source,
        "compliance_status": c.compliance_status.value,
        "compliance_label": COMPLIANCE_LABELS[c.compliance_status],
        "compliance_note": c.compliance_note,
        "dispute_risk_pct": d(c.dispute_risk_pct),
        "auto_delivery_possible": c.auto_delivery_possible,
    }


def product(p: Product, *, stock: dict[str, int] | None = None) -> dict[str, Any]:
    status = compliance_of(p)
    return {
        "id": p.id,
        "sku": p.sku,
        "name": p.name,
        "category": {"id": p.category.id, "code": p.category.code, "name": p.category.name, "group": p.category.group},
        "description": p.description,
        "region": p.region,
        "face_value": d(p.face_value),
        "face_currency": p.face_currency,
        "delivery_type": p.delivery_type.value,
        "delivery_time": p.delivery_time,
        "activation_notes": p.activation_notes,
        "buyer_instructions": p.buyer_instructions,
        "required_buyer_data": p.required_buyer_data,
        "status": p.status.value,
        "compliance_status": status.value,
        "compliance_label": COMPLIANCE_LABELS[status],
        "supplier_product_id": p.preferred_supplier_product_id,
        "supplier_quantity": p.supplier_quantity,
        "manual_unit_cost": d(p.manual_unit_cost),
        "auto_purchase_allowed": p.auto_purchase_allowed,
        "image_template": p.image_template,
        "pricing": {
            "status": p.pricing_status,
            "status_label": PRICING_LABELS.get(p.pricing_status, p.pricing_status),
            "current_price": d(p.current_price),
            "min_price": d(p.min_price),
            "recommended_price": d(p.recommended_price),
            "full_cost": d(p.full_cost),
            "expected_profit": d(p.expected_profit),
            "expected_margin_pct": d(p.expected_margin_pct),
            "notes": p.pricing_notes or [],
            "priced_at": dt(p.priced_at),
        },
        "stock": stock,
        "version": p.price_version,
        "updated_at": dt(p.updated_at),
    }


def supplier(s: Supplier) -> dict[str, Any]:
    cls = registry.adapter_class(s.adapter)
    return {
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "website": s.website,
        "adapter": s.adapter,
        "adapter_title": cls.title,
        "adapter_description": cls.description,
        "capabilities": cls.capabilities.__dict__,
        "categories": s.categories,
        "integration_method": s.integration_method,
        "status": s.status.value,
        "status_label": SUPPLIER_STATUS_LABELS[s.status],
        "status_reason": s.status_reason,
        "purchase_mode": s.purchase_mode.value,
        "purchase_mode_label": PURCHASE_MODE_LABELS[s.purchase_mode],
        "currency": s.currency,
        "balance": d(s.balance),
        "balance_currency": s.balance_currency,
        "balance_checked_at": dt(s.balance_checked_at),
        "max_single_purchase": d(s.max_single_purchase),
        "daily_limit": d(s.daily_limit),
        "max_operations_per_day": s.max_operations_per_day,
        "fee_pct": d(s.fee_pct),
        "fee_fixed": d(s.fee_fixed),
        "refund_policy": s.refund_policy,
        "policy_note": s.policy_note,
        "verification": s.verification,
        "last_check_at": dt(s.last_check_at),
        "last_sync_at": dt(s.last_sync_at),
        "last_error": s.last_error,
        "success_count": s.success_count,
        "error_count": s.error_count,
    }


def supplier_product(sp: SupplierProduct) -> dict[str, Any]:
    return {
        "id": sp.id,
        "supplier_id": sp.supplier_id,
        "supplier": sp.supplier.name,
        "external_id": sp.external_id,
        "name": sp.name,
        "category": sp.category,
        "price": d(sp.price),
        "price_unit": sp.price_unit,
        "currency": sp.currency,
        "min_quantity": sp.min_quantity,
        "max_quantity": sp.max_quantity,
        "region": sp.region,
        "available": sp.available,
        "compliance_status": sp.compliance_status.value,
        "compliance_label": COMPLIANCE_LABELS[sp.compliance_status],
        "last_seen_at": dt(sp.last_seen_at),
        "price_changed_at": dt(sp.price_changed_at),
    }


def code(c: DigitalCode) -> dict[str, Any]:
    return {
        "id": c.id,
        "mask": c.code_mask,
        "status": c.status.value,
        "is_test": c.is_test,
        "revealed_count": c.revealed_count,
        "issued_at": dt(c.issued_at),
    }


def supplier_order(so: SupplierOrder) -> dict[str, Any]:
    return {
        "id": so.id,
        "supplier_id": so.supplier_id,
        "status": so.status.value,
        "external_id": so.external_id,
        "quantity": so.quantity,
        "cost": d(so.cost),
        "currency": so.currency,
        "cost_rub": d(so.cost_rub),
        "is_test": so.is_test,
        "last_error": so.last_error,
        "message": (so.response or {}).get("message"),
        "created_at": dt(so.created_at),
    }


def order(o: Order, *, detailed: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": o.id,
        "number": o.number,
        "external_id": o.external_id,
        "marketplace": o.marketplace,
        "source": o.source,
        "buyer_name": o.buyer_name,
        "status": o.status.value,
        "status_label": ORDER_STATUS_LABELS[o.status],
        "status_reason": o.status_reason,
        "needs_attention": o.needs_attention,
        "automation_paused": o.automation_paused,
        "total_amount": d(o.total_amount),
        "marketplace_fee": d(o.marketplace_fee),
        "cost_total": d(o.cost_total),
        "net_profit": d(o.net_profit),
        "is_test": o.is_test,
        "placed_at": dt(o.placed_at),
        "delivered_at": dt(o.delivered_at),
        "completed_at": dt(o.completed_at),
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product": i.product.name,
                "sku": i.product.sku,
                "delivery_type": i.product.delivery_type.value,
                "quantity": i.quantity,
                "unit_price": d(i.unit_price),
                "unit_cost": d(i.unit_cost),
                "fulfilled_quantity": i.fulfilled_quantity,
                "listing_id": i.listing_id,
            }
            for i in o.items
        ],
    }
    if detailed:
        data["buyer_data"] = {k: v for k, v in (o.buyer_data or {}).items() if not k.startswith("_")}
        data["notes"] = o.notes
        data["review_received_at"] = dt(o.review_received_at)
        data["buyer_confirmed_at"] = dt(o.buyer_confirmed_at)
    return data


def listing(lst: Listing) -> dict[str, Any]:
    return {
        "id": lst.id,
        "product_id": lst.product_id,
        "product": lst.product.name,
        "marketplace": lst.marketplace,
        "external_id": lst.external_id,
        "external_url": lst.external_url,
        "marketplace_category": lst.marketplace_category,
        "title": lst.title,
        "description": lst.description,
        "price": d(lst.price),
        "quantity": lst.quantity,
        "status": lst.status.value,
        "status_label": LISTING_STATUS_LABELS[lst.status],
        "status_reason": lst.status_reason,
        "version": lst.version,
        "preview_confirmed_at": dt(lst.preview_confirmed_at),
        "published_at": dt(lst.published_at),
        "relist_on_complete": lst.relist_on_complete,
        "auto_created": lst.auto_created,
        "min_price": d(lst.product.min_price),
        "recommended_price": d(lst.product.recommended_price),
        "updated_at": dt(lst.updated_at),
    }


def message(m: CustomerMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "order_id": m.order_id,
        "buyer_name": m.buyer_name,
        "direction": m.direction.value,
        "text": m.text,
        "status": m.status.value,
        "source": m.source,
        "suggested_reply": m.suggested_reply,
        "problem_hint": m.problem_hint,
        "matched_rule_id": m.matched_rule_id,
        "handled_by": m.handled_by,
        "handled_at": dt(m.handled_at),
        "received_at": dt(m.received_at),
    }


def review(r: Review) -> dict[str, Any]:
    return {
        "id": r.id,
        "order_id": r.order_id,
        "rating": r.rating,
        "text": r.text,
        "sentiment": r.sentiment.value,
        "created_at": dt(r.created_at),
    }


def snapshot(s: MarketPriceSnapshot) -> dict[str, Any]:
    return {
        "id": s.id,
        "source": s.source,
        "competitor_min": d(s.competitor_min),
        "competitor_median": d(s.competitor_median),
        "competitor_max": d(s.competitor_max),
        "offers_count": s.offers_count,
        "note": s.note,
        "observed_at": dt(s.observed_at),
        "recorded_by": s.recorded_by,
    }


def audit_entry(a: AuditLog) -> dict[str, Any]:
    return {
        "id": a.id,
        "actor_type": a.actor_type,
        "actor": a.actor_name or a.actor_id,
        "action": a.action,
        "entity_type": a.entity_type,
        "entity_id": a.entity_id,
        "ip": a.ip,
        "details": a.details,
        "created_at": dt(a.created_at),
    }


def automation_entry(a: AutomationLog) -> dict[str, Any]:
    return {
        "id": a.id,
        "feature": a.feature,
        "action": a.action,
        "result": a.result.value,
        "message": a.message,
        "order_id": a.order_id,
        "created_at": dt(a.created_at),
    }


def sync_run(r: SyncRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "source": r.source,
        "kind": r.kind,
        "status": r.status.value,
        "records_received": r.records_received,
        "records_saved": r.records_saved,
        "errors_count": r.errors_count,
        "message": r.message,
        "started_at": dt(r.started_at),
        "finished_at": dt(r.finished_at),
    }


def notification(n: Notification) -> dict[str, Any]:
    return {
        "id": n.id,
        "kind": n.kind,
        "severity": n.severity.value,
        "title": n.title,
        "body": n.body,
        "status": n.status.value,
        "attempts": n.attempts,
        "last_error": n.last_error,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "created_at": dt(n.created_at),
        "sent_at": dt(n.sent_at),
    }
