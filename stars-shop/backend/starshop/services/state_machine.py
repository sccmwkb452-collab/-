"""Order finite-state machine.

    created ──► pending_payment ──► paid ──► processing ──► completed
       │              │              │            │              │
       ▼              ▼              ▼            ▼              ▼
    cancelled ◄───────┘        refund_pending ◄─ failed    refund_pending
       │                             │
       └──► paid (late payment       ▼
            confirmed by provider) refunded

Every transition goes through ``transition()`` which validates it, stamps
timestamps and writes an ``OrderEvent`` — there is no other code path that
changes ``Order.status``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import ActorType, OrderStatus
from ..database.models import Order, OrderEvent
from ..shared.errors import InvalidTransition
from ..shared.timeutil import utcnow

S = OrderStatus

TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    S.created: frozenset({S.pending_payment, S.cancelled}),
    S.pending_payment: frozenset({S.paid, S.cancelled}),
    S.paid: frozenset({S.processing, S.refund_pending}),
    S.processing: frozenset({S.completed, S.failed}),
    S.failed: frozenset({S.processing, S.refund_pending, S.completed}),
    S.completed: frozenset({S.refund_pending}),
    S.refund_pending: frozenset({S.refunded}),
    S.refunded: frozenset(),
    # Only a provider-confirmed late payment can revive a cancelled order.
    S.cancelled: frozenset({S.paid}),
}

OPEN_STATUSES = frozenset({S.created, S.pending_payment})
PAID_STATUSES = frozenset({S.paid, S.processing, S.completed, S.failed, S.refund_pending})
TERMINAL_STATUSES = frozenset({S.completed, S.refunded, S.cancelled})

# Filters of the "My orders" screen.
STATUS_GROUPS: dict[str, frozenset[OrderStatus]] = {
    "pending": frozenset({S.created, S.pending_payment}),
    "processing": frozenset({S.paid, S.processing, S.failed}),
    "completed": frozenset({S.completed}),
    "closed": frozenset({S.cancelled, S.refund_pending, S.refunded}),
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in TRANSITIONS[current]


def add_event(
    session: AsyncSession,
    order: Order,
    event_type: str,
    *,
    actor_type: ActorType = ActorType.system,
    actor_id: str | int | None = None,
    message: str | None = None,
    data: dict[str, Any] | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    public: bool = True,
) -> OrderEvent:
    event = OrderEvent(
        order_id=order.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        message=message,
        actor_type=actor_type,
        actor_id=str(actor_id) if actor_id is not None else None,
        is_public=public,
        data=data,
    )
    session.add(event)
    return event


def transition(
    session: AsyncSession,
    order: Order,
    target: OrderStatus,
    *,
    actor_type: ActorType = ActorType.system,
    actor_id: str | int | None = None,
    message: str | None = None,
    data: dict[str, Any] | None = None,
    event_type: str = "status_changed",
) -> None:
    current = OrderStatus(order.status)
    if not can_transition(current, target):
        raise InvalidTransition(details={"from": current.value, "to": target.value})
    now = utcnow()
    order.status = target
    if target is S.paid:
        order.paid_at = order.paid_at or now
        order.cancelled_at = None
    elif target is S.completed:
        order.completed_at = now
        order.failure_reason = None
    elif target is S.cancelled:
        order.cancelled_at = now
    elif target is S.refunded:
        order.refunded_at = now
    add_event(
        session,
        order,
        event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        message=message,
        data=data,
        from_status=current.value,
        to_status=target.value,
    )
