from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import case, func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.db.models import Job, JobEvent, JobItem
from smart_email_manager.domain.enums import JobItemStatus, JobStatus


@dataclass(frozen=True)
class LeasedJobItem:
    id: uuid.UUID
    job_id: uuid.UUID
    job_type: str
    item_key: str
    subject_type: str
    subject_id: uuid.UUID | None
    payload: dict[str, Any]
    attempt_count: int
    max_attempts: int
    lease_owner: str


LEASE_SQL = text(
    """
    WITH candidate AS (
        SELECT ji.id
        FROM job_items AS ji
        JOIN jobs AS j ON j.id = ji.job_id
        WHERE ji.status IN ('pending', 'retry_wait')
          AND (ji.run_after IS NULL OR ji.run_after <= now())
          AND (ji.lease_expires_at IS NULL OR ji.lease_expires_at < now())
          AND j.status IN ('queued', 'running')
          AND j.cancel_requested_at IS NULL
        ORDER BY j.priority DESC, ji.created_at ASC, ji.id ASC
        FOR UPDATE OF ji SKIP LOCKED
        LIMIT 1
    )
    UPDATE job_items AS ji
    SET status = 'running',
        lease_owner = :worker_id,
        lease_expires_at = now() + (:lease_seconds * interval '1 second'),
        attempt_count = ji.attempt_count + 1,
        started_at = COALESCE(ji.started_at, now()),
        updated_at = now()
    FROM candidate
    WHERE ji.id = candidate.id
    RETURNING
        ji.id,
        ji.job_id,
        ji.item_key,
        ji.subject_type,
        ji.subject_id,
        ji.payload,
        ji.attempt_count,
        ji.max_attempts,
        ji.lease_owner
    """
)


async def recover_expired_leases(session: AsyncSession) -> int:
    affected_job_ids = list(
        (
            await session.scalars(
                select(JobItem.job_id)
                .where(
                    JobItem.status.in_((JobItemStatus.LEASED, JobItemStatus.RUNNING)),
                    JobItem.lease_expires_at < func.now(),
                )
                .distinct()
            )
        ).all()
    )
    if not affected_job_ids:
        await session.rollback()
        return 0

    result = await session.execute(
        update(JobItem)
        .where(
            JobItem.status.in_((JobItemStatus.LEASED, JobItemStatus.RUNNING)),
            JobItem.lease_expires_at < func.now(),
        )
        .values(
            status=case(
                (JobItem.attempt_count >= JobItem.max_attempts, JobItemStatus.FAILED),
                else_=JobItemStatus.PENDING,
            ),
            error_code=case(
                (JobItem.attempt_count >= JobItem.max_attempts, "LEASE_EXPIRED"),
                else_=JobItem.error_code,
            ),
            error_summary=case(
                (JobItem.attempt_count >= JobItem.max_attempts, "Worker lease expired too many times."),
                else_=JobItem.error_summary,
            ),
            lease_owner=None,
            lease_expires_at=None,
            updated_at=func.now(),
        )
    )
    for job_id in affected_job_ids:
        job = await session.get(Job, job_id, with_for_update=True)
        if job:
            await _refresh_job_summary(session, job)
    await session.commit()
    return int(cast(CursorResult[Any], result).rowcount or 0)


async def lease_next_item(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int,
) -> LeasedJobItem | None:
    row = (
        (
            await session.execute(
                LEASE_SQL,
                {"worker_id": worker_id, "lease_seconds": lease_seconds},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        await session.rollback()
        return None

    job = await session.get(Job, row["job_id"], with_for_update=True)
    if job is None:
        await session.rollback()
        return None
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
    session.add(
        JobEvent(
            job_id=job.id,
            job_item_id=row["id"],
            event_type="job_item.started",
            message=f"Started {row['item_key']}.",
            data={"attempt_count": row["attempt_count"], "worker_id": worker_id},
        )
    )
    await session.commit()
    return LeasedJobItem(
        id=row["id"],
        job_id=row["job_id"],
        job_type=job.job_type,
        item_key=row["item_key"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        payload=dict(row["payload"] or {}),
        attempt_count=row["attempt_count"],
        max_attempts=row["max_attempts"],
        lease_owner=row["lease_owner"],
    )


async def _refresh_job_summary(session: AsyncSession, job: Job) -> None:
    counts = (
        await session.execute(
            select(
                func.count().filter(JobItem.status == JobItemStatus.SUCCEEDED),
                func.count().filter(JobItem.status == JobItemStatus.FAILED),
                func.count().filter(JobItem.status == JobItemStatus.SKIPPED),
                func.count().filter(
                    JobItem.status.in_(
                        (
                            JobItemStatus.PENDING,
                            JobItemStatus.LEASED,
                            JobItemStatus.RUNNING,
                            JobItemStatus.RETRY_WAIT,
                        )
                    )
                ),
            ).where(JobItem.job_id == job.id)
        )
    ).one()
    succeeded, failed, skipped, unfinished = (int(value or 0) for value in counts)
    job.succeeded_count = succeeded
    job.failed_count = failed
    job.skipped_count = skipped

    if unfinished:
        return
    job.finished_at = datetime.now(UTC)
    if job.cancel_requested_at:
        job.status = JobStatus.CANCELLED
    elif failed and (succeeded or skipped):
        job.status = JobStatus.PARTIAL
    elif failed:
        job.status = JobStatus.FAILED
    else:
        job.status = JobStatus.COMPLETED

    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.finished",
            message=f"Job finished with status {job.status}.",
            data={
                "succeeded_count": succeeded,
                "failed_count": failed,
                "skipped_count": skipped,
            },
        )
    )


async def finish_item(
    session: AsyncSession,
    lease: LeasedJobItem,
    *,
    status: JobItemStatus,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> None:
    item = await session.get(JobItem, lease.id, with_for_update=True)
    if item is None:
        raise RuntimeError(f"Leased item {lease.id} disappeared")
    if item.lease_owner != lease.lease_owner:
        raise RuntimeError(f"Lease ownership changed for item {lease.id}")

    item.status = status
    item.result = result or {}
    item.error_code = error_code
    item.error_summary = error_summary
    item.finished_at = datetime.now(UTC)
    item.lease_owner = None
    item.lease_expires_at = None
    session.add(
        JobEvent(
            job_id=lease.job_id,
            job_item_id=lease.id,
            event_type=f"job_item.{status}",
            level="error" if status == JobItemStatus.FAILED else "info",
            message=error_summary or f"Finished {lease.item_key} with status {status}.",
            data=result or {},
        )
    )

    job = await session.get(Job, lease.job_id, with_for_update=True)
    if job is None:
        raise RuntimeError(f"Job {lease.job_id} disappeared")
    await session.flush()
    await _refresh_job_summary(session, job)
    await session.commit()


async def retry_item(
    session: AsyncSession,
    lease: LeasedJobItem,
    *,
    error_code: str,
    error_summary: str,
    result: dict[str, Any] | None = None,
    delay_seconds: int | None = None,
) -> None:
    if lease.attempt_count >= lease.max_attempts:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.FAILED,
            result=result,
            error_code=error_code,
            error_summary=error_summary,
        )
        return
    item = await session.get(JobItem, lease.id, with_for_update=True)
    if item is None:
        raise RuntimeError(f"Leased item {lease.id} disappeared")
    if item.lease_owner != lease.lease_owner:
        raise RuntimeError(f"Lease ownership changed for item {lease.id}")
    delay = delay_seconds or min(5 * (2 ** max(0, lease.attempt_count - 1)), 300)
    item.status = JobItemStatus.RETRY_WAIT
    item.run_after = datetime.now(UTC) + timedelta(seconds=delay)
    item.result = result or {}
    item.error_code = error_code
    item.error_summary = error_summary
    item.finished_at = None
    item.lease_owner = None
    item.lease_expires_at = None
    session.add(
        JobEvent(
            job_id=lease.job_id,
            job_item_id=lease.id,
            event_type="job_item.retry_scheduled",
            level="warning",
            message=error_summary,
            data={
                "attempt_count": lease.attempt_count,
                "max_attempts": lease.max_attempts,
                "delay_seconds": delay,
                "next_attempt": lease.attempt_count + 1,
                **(result or {}),
            },
        )
    )
    await session.commit()


async def cancel_pending_items(session: AsyncSession) -> int:
    cancelling_ids = select(Job.id).where(Job.status == JobStatus.CANCELLING)
    result = await session.execute(
        update(JobItem)
        .where(
            JobItem.job_id.in_(cancelling_ids),
            JobItem.status.in_((JobItemStatus.PENDING, JobItemStatus.RETRY_WAIT)),
        )
        .values(
            status=JobItemStatus.CANCELLED,
            finished_at=func.now(),
            updated_at=func.now(),
        )
    )
    job_ids = list((await session.scalars(cancelling_ids)).all())
    for job_id in job_ids:
        job = await session.get(Job, job_id, with_for_update=True)
        if job:
            await _refresh_job_summary(session, job)
    await session.commit()
    return int(cast(CursorResult[Any], result).rowcount or 0)
