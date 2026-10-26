"""Durable job queue on PostgreSQL.

* ``enqueue`` deduplicates by key: only one queued/running job per key exists
  (partial unique index), so a double click or a repeated event never starts
  the same work twice.
* ``claim`` uses ``FOR UPDATE SKIP LOCKED`` so several workers never take the
  same job, and sets a lease. A worker that dies leaves the lease to expire;
  ``recover_stale`` puts such jobs back in the queue (restart recovery).
* ``fail`` retries with exponential backoff up to ``max_attempts``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import JobStatus
from ..database.models import AutomationJob
from ..shared.masking import scrub_text
from ..shared.timeutil import utcnow

MAX_BACKOFF_SECONDS = 3600


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 5,
) -> int | None:
    """Returns the job id, or None when an identical job is already queued/running."""
    stmt = (
        insert(AutomationJob)
        .values(
            kind=kind,
            payload=payload or {},
            dedupe_key=dedupe_key,
            run_after=run_after or utcnow(),
            max_attempts=max_attempts,
            status=JobStatus.QUEUED,
        )
        .on_conflict_do_nothing(
            index_elements=[AutomationJob.dedupe_key],
            # literal predicate: with bind parameters PostgreSQL cannot match the partial
            # index once it switches the prepared statement to a generic plan
            index_where=text("dedupe_key IS NOT NULL AND status IN ('queued','running')"),
        )
        .returning(AutomationJob.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def claim(session: AsyncSession, worker_id: str, *, limit: int = 1, kinds: list[str] | None = None) -> list[AutomationJob]:
    now = utcnow()
    query = (
        select(AutomationJob)
        .where(AutomationJob.status == JobStatus.QUEUED, AutomationJob.run_after <= now)
        .order_by(AutomationJob.run_after, AutomationJob.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if kinds:
        query = query.where(AutomationJob.kind.in_(kinds))
    jobs = list((await session.execute(query)).scalars())
    lease = timedelta(seconds=get_settings().worker_job_lease_seconds)
    for job in jobs:
        job.status = JobStatus.RUNNING
        job.locked_by = worker_id
        job.locked_until = now + lease
        job.attempts += 1
    await session.flush()
    return jobs


async def complete(session: AsyncSession, job: AutomationJob) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = utcnow()
    job.locked_until = None
    job.last_error = None


def backoff_seconds(attempts: int) -> int:
    return min(MAX_BACKOFF_SECONDS, 15 * (2 ** max(0, attempts - 1)))


async def fail(session: AsyncSession, job: AutomationJob, error: str, *, retry: bool = True) -> bool:
    """Returns True when the job will be retried."""
    job.last_error = scrub_text(error)[:2000]
    job.locked_until = None
    if retry and job.attempts < job.max_attempts:
        job.status = JobStatus.QUEUED
        job.run_after = utcnow() + timedelta(seconds=backoff_seconds(job.attempts))
        return True
    job.status = JobStatus.FAILED
    job.finished_at = utcnow()
    return False


async def recover_stale(session: AsyncSession) -> int:
    """Jobs whose worker vanished (lease expired) go back to the queue."""
    result = await session.execute(
        update(AutomationJob)
        .where(AutomationJob.status == JobStatus.RUNNING, AutomationJob.locked_until < utcnow())
        .values(status=JobStatus.QUEUED, locked_by=None, locked_until=None, last_error="lease expired: worker restarted")
    )
    return result.rowcount or 0


async def queue_stats(session: AsyncSession) -> dict[str, int]:
    from sqlalchemy import func

    rows = await session.execute(select(AutomationJob.status, func.count()).group_by(AutomationJob.status))
    stats = {s.value: 0 for s in JobStatus}
    for status, count in rows:
        stats[status.value if hasattr(status, "value") else status] = count
    overdue = await session.execute(
        select(func.count()).where(
            or_(
                and_(AutomationJob.status == JobStatus.QUEUED, AutomationJob.run_after < utcnow() - timedelta(minutes=10)),
                and_(AutomationJob.status == JobStatus.RUNNING, AutomationJob.locked_until < utcnow()),
            )
        )
    )
    stats["overdue"] = overdue.scalar_one()
    return stats
