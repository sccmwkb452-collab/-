"""Data retention: old logs, notifications, finished jobs and buyer messages
are deleted after the configured number of days (orders, transactions and the
audit of money operations are kept)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import JobStatus, NotificationStatus
from ..database.models import AutomationJob, AutomationLog, CustomerMessage, Notification, OneTimeToken, SyncRun, WebSession
from ..shared.timeutil import utcnow


async def cleanup(session: AsyncSession) -> dict[str, int]:
    s = get_settings()
    now = utcnow()
    results: dict[str, int] = {}

    async def run(name: str, stmt) -> None:
        results[name] = (await session.execute(stmt)).rowcount or 0

    await run("automation_logs", delete(AutomationLog).where(AutomationLog.created_at < now - timedelta(days=s.retention_logs_days)))
    await run("sync_runs", delete(SyncRun).where(SyncRun.started_at < now - timedelta(days=s.retention_logs_days)))
    await run(
        "notifications",
        delete(Notification).where(
            Notification.created_at < now - timedelta(days=s.retention_notifications_days),
            Notification.status != NotificationStatus.PENDING,
        ),
    )
    await run(
        "jobs",
        delete(AutomationJob).where(
            AutomationJob.finished_at < now - timedelta(days=14), AutomationJob.status.in_([JobStatus.SUCCEEDED, JobStatus.CANCELLED])
        ),
    )
    await run("messages", delete(CustomerMessage).where(CustomerMessage.received_at < now - timedelta(days=s.retention_messages_days)))
    await run("sessions", delete(WebSession).where(WebSession.expires_at < now - timedelta(days=7)))
    await run("tokens", delete(OneTimeToken).where(OneTimeToken.expires_at < now - timedelta(days=1)))
    return results
