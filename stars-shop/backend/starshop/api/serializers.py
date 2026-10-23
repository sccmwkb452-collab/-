"""ORM -> JSON-ready dicts. Kept explicit so that internal fields (costs,
provider payloads, admin notes) can never leak into public responses."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..database.enums import DeliveryStatus, OrderStatus, PaymentStatus, ProductKind
from ..database.models import (
    AdminAuditLog,
    AdminUser,
    DeliveryTask,
    Order,
    OrderEvent,
    Payment,
    Product,
    PromoCode,
    SupportMessage,
    SupportTicket,
    User,
)
from ..notifications.templates import STATUS_LABELS
from ..payments.registry import get_payment_provider
from ..services.state_machine import OPEN_STATUSES
from ..shared.masking import mask_username
from ..shared.money import money


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _m(value: Decimal | None) -> str | None:
    return str(money(value)) if value is not None else None


def product_public(p: Product) -> dict[str, Any]:
    per_star = (
        p.price_per_star if p.kind == ProductKind.custom else (money(p.price) / p.stars_amount if p.price and p.stars_amount else None)
    )
    return {
        "id": p.id,
        "kind": p.kind,
        "title": p.title,
        "badge": p.badge,
        "stars_amount": p.stars_amount,
        "price": _m(p.price),
        "price_per_star": str(Decimal(per_star).quantize(Decimal("0.0001"))) if per_star is not None else None,
        "min_stars": p.min_stars,
        "max_stars": p.max_stars,
        "is_popular": p.is_popular,
    }


def product_admin(p: Product) -> dict[str, Any]:
    data = product_public(p)
    data.update(
        {
            "is_active": p.is_active,
            "is_archived": p.is_archived,
            "sort_order": p.sort_order,
            "cost_per_star": str(p.cost_per_star) if p.cost_per_star is not None else None,
            "cost_source": p.cost_source,
            "cost_updated_at": _iso(p.cost_updated_at),
            "created_at": _iso(p.created_at),
            "updated_at": _iso(p.updated_at),
        }
    )
    return data


def provider_title(name: str) -> str:
    try:
        return get_payment_provider(name).title
    except Exception:
        return name


def payment_public(p: Payment) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "provider": p.provider,
        "status": p.status,
        "amount": _m(p.amount),
        "currency": p.currency,
        "pay_url": p.pay_url if p.status in (PaymentStatus.created, PaymentStatus.pending) else None,
        "pay_url_kind": p.pay_url_kind,
        "expires_at": _iso(p.expires_at),
        "is_demo": p.is_demo,
    }


def event_public(e: OrderEvent) -> dict[str, Any]:
    return {"type": e.event_type, "status": e.to_status, "message": e.message, "at": _iso(e.created_at)}


def order_summary(o: Order) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "number": o.number,
        "status": o.status,
        "status_label": STATUS_LABELS.get(o.status, o.status),
        "created_at": _iso(o.created_at),
        "stars_amount": o.stars_amount,
        "total": _m(o.total),
        "currency": o.currency,
        "recipient": {
            "type": o.recipient_type,
            "masked": "Себе" if o.recipient_type == "self" else mask_username(o.recipient_username),
        },
        "payment_provider": o.payment_provider,
        "payment_method": provider_title(o.payment_provider),
        "mode": o.mode,
    }


def order_detail(o: Order, *, payments: list[Payment], events: list[OrderEvent], task: DeliveryTask | None) -> dict[str, Any]:
    data = order_summary(o)
    open_payment = next((p for p in reversed(payments) if p.status in (PaymentStatus.created, PaymentStatus.pending)), None)
    data.update(
        {
            "updated_at": _iso(o.updated_at),
            "paid_at": _iso(o.paid_at),
            "completed_at": _iso(o.completed_at),
            "expires_at": _iso(o.expires_at),
            "recipient": {**data["recipient"], "username": o.recipient_username, "name": o.recipient_name},
            "amounts": {
                "unit_price": str(o.unit_price),
                "subtotal": _m(o.subtotal),
                "discount": _m(o.discount_amount),
                "bonus_spent": _m(o.bonus_spent),
                "fee": _m(o.fee_amount),
                "total": _m(o.total),
                "currency": o.currency,
            },
            "can_pay": o.status in OPEN_STATUSES,
            "can_cancel": o.status in OPEN_STATUSES,
            "payment": payment_public(open_payment) if open_payment else None,
            "timeline": [event_public(e) for e in events if e.is_public],
            "delivery": {"status": _public_delivery_status(task)} if task else None,
            "problem": o.status == OrderStatus.failed,
        }
    )
    return data


def _public_delivery_status(task: DeliveryTask) -> str:
    if task.status == DeliveryStatus.succeeded:
        return "delivered"
    if task.status in (DeliveryStatus.failed,):
        return "failed"
    if task.status == DeliveryStatus.cancelled:
        return "cancelled"
    return "in_progress"


# --- admin ---------------------------------------------------------------------


def user_admin(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "username": u.username,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "display_name": u.display_name,
        "photo_url": u.photo_url,
        "language_code": u.language_code,
        "is_premium": u.is_premium,
        "bot_started": u.bot_started,
        "is_blocked": u.is_blocked,
        "blocked_reason": u.blocked_reason,
        "bonus_balance": _m(u.bonus_balance),
        "referral_code": u.referral_code,
        "referred_by_id": u.referred_by_id,
        "first_seen_at": _iso(u.first_seen_at),
        "last_seen_at": _iso(u.last_seen_at),
    }


def order_admin(o: Order, user: User | None = None) -> dict[str, Any]:
    data = order_summary(o)
    data.update(
        {
            "user_id": o.user_id,
            "user": {"telegram_id": user.telegram_id, "username": user.username, "display_name": user.display_name} if user else None,
            "recipient": {
                "type": o.recipient_type,
                "username": o.recipient_username,
                "telegram_id": o.recipient_telegram_id,
                "name": o.recipient_name,
            },
            "product_id": o.product_id,
            "product_kind": o.product_kind,
            "unit_price": str(o.unit_price),
            "subtotal": _m(o.subtotal),
            "discount": _m(o.discount_amount),
            "bonus_spent": _m(o.bonus_spent),
            "fee": _m(o.fee_amount),
            "cost": _m(o.cost_amount),
            "delivery_provider": o.delivery_provider,
            "promo_code_id": o.promo_code_id,
            "failure_reason": o.failure_reason,
            "updated_at": _iso(o.updated_at),
            "paid_at": _iso(o.paid_at),
            "completed_at": _iso(o.completed_at),
            "cancelled_at": _iso(o.cancelled_at),
            "refunded_at": _iso(o.refunded_at),
            "expires_at": _iso(o.expires_at),
        }
    )
    return data


def payment_admin(p: Payment) -> dict[str, Any]:
    return {
        **payment_public(p),
        "provider_payment_id": p.provider_payment_id,
        "paid_amount": p.paid_amount,
        "paid_asset": p.paid_asset,
        "is_duplicate": p.is_duplicate,
        "confirmed_at": _iso(p.confirmed_at),
        "refunded_at": _iso(p.refunded_at),
        "refund_reference": p.refund_reference,
        "refund_reason": p.refund_reason,
        "refund_attempts": p.refund_attempts,
        "last_error": p.last_error,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
        "pay_url": p.pay_url,
    }


def task_admin(t: DeliveryTask) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "provider": t.provider,
        "status": t.status,
        "attempts": t.attempts,
        "max_attempts": t.max_attempts,
        "external_id": t.external_id,
        "next_attempt_at": _iso(t.next_attempt_at),
        "last_error": t.last_error,
        "result": t.result,
        "completed_at": _iso(t.completed_at),
        "created_at": _iso(t.created_at),
    }


def event_admin(e: OrderEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "type": e.event_type,
        "from_status": e.from_status,
        "to_status": e.to_status,
        "message": e.message,
        "actor_type": e.actor_type,
        "actor_id": e.actor_id,
        "is_public": e.is_public,
        "data": e.data,
        "at": _iso(e.created_at),
    }


def promo_admin(p: PromoCode, used: int = 0) -> dict[str, Any]:
    return {
        "id": p.id,
        "code": p.code,
        "description": p.description,
        "kind": p.kind,
        "value": str(p.value),
        "max_discount": _m(p.max_discount),
        "min_order_amount": _m(p.min_order_amount),
        "starts_at": _iso(p.starts_at),
        "expires_at": _iso(p.expires_at),
        "max_uses": p.max_uses,
        "per_user_limit": p.per_user_limit,
        "first_order_only": p.first_order_only,
        "is_active": p.is_active,
        "used": used,
        "created_at": _iso(p.created_at),
    }


def admin_user(a: AdminUser) -> dict[str, Any]:
    return {
        "id": a.id,
        "telegram_id": a.telegram_id,
        "username": a.username,
        "display_name": a.display_name,
        "role": a.role,
        "is_active": a.is_active,
        "last_login_at": _iso(a.last_login_at),
    }


def audit_admin(log: AdminAuditLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "admin_id": log.admin_id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "summary": log.summary,
        "before": log.before,
        "after": log.after,
        "ip": log.ip,
        "at": _iso(log.created_at),
    }


def ticket(t: SupportTicket, messages: list[SupportMessage] | None = None, *, admin: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": t.id,
        "subject": t.subject,
        "status": t.status,
        "order_id": str(t.order_id) if t.order_id else None,
        "created_at": _iso(t.created_at),
        "last_message_at": _iso(t.last_message_at),
    }
    if admin:
        data["user_id"] = t.user_id
    if messages is not None:
        data["messages"] = [
            {"id": m.id, "author": m.author_type, "text": m.text, "at": _iso(m.created_at), **({"admin_id": m.admin_id} if admin else {})}
            for m in messages
        ]
    return data
