from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.db.models import (
    Account,
    AccountForwarding,
    AccountSecret,
    Job,
    JobEvent,
    JobItem,
    RetentionPolicy,
)
from smart_email_manager.domain.enums import JobItemStatus, JobStatus, LifecycleStatus, TokenStatus


async def create_health_check_job(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    limit: int,
    mode: str,
    idempotency_key: str | None,
) -> Job:
    if idempotency_key:
        existing = await session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing:
            return existing

    statement = select(Account.id).where(Account.lifecycle_status == LifecycleStatus.ACTIVE)
    if account_ids:
        statement = statement.where(Account.id.in_(account_ids))
    statement = statement.order_by(Account.created_at, Account.id).limit(limit)
    selected_ids = list((await session.scalars(statement)).all())

    job = Job(
        job_type="account.health_check",
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        payload={"mode": mode, "requested_account_ids": [str(item) for item in account_ids]},
        total_count=len(selected_ids),
    )
    session.add(job)
    await session.flush()

    for account_id in selected_ids:
        session.add(
            JobItem(
                job_id=job.id,
                item_key=f"account:{account_id}",
                subject_type="account",
                subject_id=account_id,
                payload={"mode": mode},
            )
        )

    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.created",
            message=f"Created {mode} health check for {len(selected_ids)} account(s).",
            data={"total_count": len(selected_ids)},
        )
    )

    if not selected_ids:
        job.status = JobStatus.COMPLETED
        job.started_at = datetime.now(UTC)
        job.finished_at = job.started_at
        job.result = {"message": "No active accounts matched the requested scope."}
    await session.commit()
    await session.refresh(job)
    return job


async def create_token_refresh_job(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    failed_only: bool,
    limit: int,
    idempotency_key: str | None = None,
    commit: bool = True,
) -> Job:
    if idempotency_key:
        existing = await session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing:
            return existing

    statement = (
        select(Account.id)
        .join(AccountSecret, AccountSecret.account_id == Account.id)
        .where(
            Account.lifecycle_status == LifecycleStatus.ACTIVE,
            AccountSecret.refresh_token_ciphertext.is_not(None),
        )
    )
    if account_ids:
        statement = statement.where(Account.id.in_(account_ids))
    if failed_only:
        statement = statement.where(Account.token_status == TokenStatus.FAILED)
    statement = statement.order_by(Account.created_at, Account.id).limit(limit)
    selected_ids = list((await session.scalars(statement)).all())

    job = Job(
        job_type="account.token_refresh",
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        payload={
            "requested_account_ids": [str(item) for item in account_ids],
            "failed_only": failed_only,
        },
        total_count=len(selected_ids),
    )
    session.add(job)
    await session.flush()

    for account_id in selected_ids:
        session.add(
            JobItem(
                job_id=job.id,
                item_key=f"account:{account_id}",
                subject_type="account",
                subject_id=account_id,
            )
        )
    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.created",
            message=f"Created token refresh for {len(selected_ids)} account(s).",
            data={"total_count": len(selected_ids), "failed_only": failed_only},
        )
    )

    if not selected_ids:
        job.status = JobStatus.COMPLETED
        job.started_at = datetime.now(UTC)
        job.finished_at = job.started_at
        job.result = {"message": "No refreshable accounts matched the requested scope."}
    if commit:
        await session.commit()
        await session.refresh(job)
    else:
        await session.flush()
    return job


async def create_retention_sync_job(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    limit: int,
    idempotency_key: str | None = None,
    commit: bool = True,
) -> Job:
    if idempotency_key:
        existing = await session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing:
            return existing
    statement = (
        select(Account.id)
        .join(RetentionPolicy, RetentionPolicy.account_id == Account.id)
        .where(
            Account.lifecycle_status == LifecycleStatus.ACTIVE,
            RetentionPolicy.enabled.is_(True),
        )
    )
    if account_ids:
        statement = statement.where(Account.id.in_(account_ids))
    selected_ids = list((await session.scalars(statement.order_by(Account.created_at).limit(limit))).all())
    job = Job(
        job_type="account.retention_sync",
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        payload={"requested_account_ids": [str(item) for item in account_ids]},
        total_count=len(selected_ids),
    )
    session.add(job)
    await session.flush()
    for account_id in selected_ids:
        session.add(
            JobItem(
                job_id=job.id,
                item_key=f"account:{account_id}",
                subject_type="account",
                subject_id=account_id,
            )
        )
    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.created",
            message=f"Created retention sync for {len(selected_ids)} account(s).",
            data={"total_count": len(selected_ids)},
        )
    )
    if not selected_ids:
        job.status = JobStatus.COMPLETED
        job.started_at = datetime.now(UTC)
        job.finished_at = job.started_at
        job.result = {"message": "No retention-enabled accounts matched the requested scope."}
    if commit:
        await session.commit()
        await session.refresh(job)
    else:
        await session.flush()
    return job


async def create_forwarding_job(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    limit: int,
    idempotency_key: str | None = None,
    commit: bool = True,
) -> Job:
    if idempotency_key:
        existing = await session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing:
            return existing
    statement = (
        select(Account.id)
        .join(AccountForwarding, AccountForwarding.account_id == Account.id)
        .where(
            Account.lifecycle_status == LifecycleStatus.ACTIVE,
            AccountForwarding.enabled.is_(True),
        )
    )
    if account_ids:
        statement = statement.where(Account.id.in_(account_ids))
    selected_ids = list((await session.scalars(statement.order_by(Account.created_at).limit(limit))).all())
    job = Job(
        job_type="account.forwarding_scan",
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        payload={"requested_account_ids": [str(item) for item in account_ids]},
        total_count=len(selected_ids),
    )
    session.add(job)
    await session.flush()
    for account_id in selected_ids:
        session.add(
            JobItem(
                job_id=job.id,
                item_key=f"account:{account_id}",
                subject_type="account",
                subject_id=account_id,
            )
        )
    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.created",
            message=f"Created forwarding scan for {len(selected_ids)} account(s).",
            data={"total_count": len(selected_ids)},
        )
    )
    if not selected_ids:
        job.status = JobStatus.COMPLETED
        job.started_at = datetime.now(UTC)
        job.finished_at = job.started_at
        job.result = {"message": "No forwarding-enabled accounts matched the requested scope."}
    if commit:
        await session.commit()
        await session.refresh(job)
    else:
        await session.flush()
    return job


async def get_job_or_404(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await session.get(Job, job_id)
    if not job:
        raise ApiProblem(
            status=404,
            code="JOB_NOT_FOUND",
            title="Job not found",
            detail=f"No job exists with id {job_id}.",
        )
    return job


async def list_jobs(
    session: AsyncSession,
    *,
    limit: int,
    status: str | None,
) -> list[Job]:
    statement = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status:
        statement = statement.where(Job.status == status)
    return list((await session.scalars(statement)).all())


async def list_job_events(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    after_sequence: int = 0,
    limit: int = 200,
) -> list[JobEvent]:
    await get_job_or_404(session, job_id)
    statement = (
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.sequence > after_sequence)
        .order_by(JobEvent.sequence)
        .limit(limit)
    )
    return list((await session.scalars(statement)).all())


async def request_job_cancel(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await get_job_or_404(session, job_id)
    if job.status in {JobStatus.COMPLETED, JobStatus.PARTIAL, JobStatus.FAILED, JobStatus.CANCELLED}:
        return job
    now = datetime.now(UTC)
    job.cancel_requested_at = now
    job.status = JobStatus.CANCELLING
    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.cancel_requested",
            message="Cancellation requested.",
        )
    )
    await session.commit()
    await session.refresh(job)
    return job


async def request_job_pause(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await get_job_or_404(session, job_id)
    if job.status in {
        JobStatus.COMPLETED,
        JobStatus.PARTIAL,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.PAUSED,
    }:
        return job
    if job.status == JobStatus.CANCELLING:
        raise ApiProblem(
            status=409,
            code="JOB_CANCELLING",
            title="Job is cancelling",
            detail="A cancelling job cannot be paused.",
        )
    job.status = JobStatus.PAUSING
    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.pause_requested",
            message="Pause requested; running items may finish their current attempt.",
        )
    )
    await session.commit()
    await session.refresh(job)
    return job


async def finalize_pausing_jobs(session: AsyncSession) -> int:
    jobs = list(
        (
            await session.scalars(
                select(Job)
                .where(Job.status == JobStatus.PAUSING)
                .with_for_update(skip_locked=True)
                .limit(100)
            )
        ).all()
    )
    paused = 0
    for job in jobs:
        running = await session.scalar(
            select(func.count())
            .select_from(JobItem)
            .where(
                JobItem.job_id == job.id,
                JobItem.status.in_((JobItemStatus.LEASED, JobItemStatus.RUNNING)),
            )
        )
        if running:
            continue
        job.status = JobStatus.PAUSED
        session.add(
            JobEvent(
                job_id=job.id,
                event_type="job.paused",
                message="Job paused before leasing another item.",
            )
        )
        paused += 1
    if jobs:
        await session.commit()
    else:
        await session.rollback()
    return paused


async def resume_job(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await get_job_or_404(session, job_id)
    if job.status != JobStatus.PAUSED:
        raise ApiProblem(
            status=409,
            code="JOB_NOT_PAUSED",
            title="Job is not paused",
            detail="Only paused jobs can be resumed.",
        )
    job.status = JobStatus.RUNNING if job.started_at else JobStatus.QUEUED
    session.add(
        JobEvent(
            job_id=job.id,
            event_type="job.resumed",
            message="Job resumed.",
        )
    )
    await session.commit()
    await session.refresh(job)
    return job
