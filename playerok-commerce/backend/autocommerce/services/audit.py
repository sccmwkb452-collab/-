"""Audit trail of administrator and system actions. Details are scrubbed of
secrets before they are stored."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import LogResult
from ..database.models import AuditLog, AutomationLog
from ..shared.masking import scrub


@dataclass(frozen=True)
class Actor:
    """Who performs an action: a web user, a Telegram user, the system or the CLI."""

    type: str
    id: str | None = None
    name: str | None = None
    ip: str | None = None
    user_id: int | None = None
    permissions: frozenset[str] = frozenset()

    @property
    def label(self) -> str:
        if self.type == "system":
            return "система"
        return f"{self.name or self.id or self.type}"

    def can(self, permission: str) -> bool:
        return self.type in ("system", "cli") or "*" in self.permissions or permission in self.permissions


SYSTEM = Actor(type="system", name="система")
CLI = Actor(type="cli", name="cli")


async def audit(
    session: AsyncSession,
    actor: Actor,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: Any = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_type=actor.type,
        actor_id=actor.id,
        actor_name=actor.name,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        ip=actor.ip,
        details=scrub(details or {}),
    )
    session.add(entry)
    return entry


async def automation_log(
    session: AsyncSession,
    feature: str,
    action: str,
    result: LogResult,
    message: str = "",
    *,
    order_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AutomationLog:
    entry = AutomationLog(
        feature=feature, action=action, result=result, message=message[:4000], order_id=order_id, details=scrub(details or {})
    )
    session.add(entry)
    return entry
