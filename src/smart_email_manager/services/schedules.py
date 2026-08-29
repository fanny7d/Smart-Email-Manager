from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.forwarding import ForwardingJobCreate
from smart_email_manager.api.schemas.refresh import ScheduleWrite, TokenRefreshJobCreate
from smart_email_manager.api.schemas.retention import RetentionSyncJobCreate
from smart_email_manager.db.models import Schedule
from smart_email_manager.services.jobs import (
    create_forwarding_job,
    create_retention_sync_job,
    create_token_refresh_job,
)


def next_schedule_run(expression: str, timezone_name: str, *, after: datetime | None = None) -> datetime:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ApiProblem(
            status=422,
            code="SCHEDULE_TIMEZONE_INVALID",
            title="Schedule timezone is invalid",
            detail=f"Unknown IANA timezone: {timezone_name}.",
        ) from exc
    if not croniter.is_valid(expression):
        raise ApiProblem(
            status=422,
            code="SCHEDULE_CRON_INVALID",
            title="Schedule cron expression is invalid",
            detail="Use a standard five-field cron expression.",
        )
    base = (after or datetime.now(UTC)).astimezone(timezone)
    next_local = croniter(expression, base).get_next(datetime)
    if not isinstance(next_local, datetime):
        raise RuntimeError("croniter returned a non-datetime schedule value")
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=timezone)
    return next_local.astimezone(UTC)


def _validated_payload(
    task_type: str,
    payload: dict[str, object],
) -> TokenRefreshJobCreate | RetentionSyncJobCreate | ForwardingJobCreate:
    if task_type not in {"token_refresh", "retention_sync", "forwarding"}:
        raise ApiProblem(
            status=422,
            code="SCHEDULE_TASK_TYPE_INVALID",
            title="Schedule task type is invalid",
            detail="Supported task types are token_refresh, retention_sync and forwarding.",
        )
    try:
        if task_type == "token_refresh":
            return TokenRefreshJobCreate.model_validate(payload)
        if task_type == "retention_sync":
            return RetentionSyncJobCreate.model_validate(payload)
        return ForwardingJobCreate.model_validate(payload)
    except ValueError as exc:
        raise ApiProblem(
            status=422,
            code="SCHEDULE_PAYLOAD_INVALID",
            title="Schedule payload is invalid",
            detail=f"The payload does not match the {task_type} schedule schema.",
        ) from exc


async def list_schedules(session: AsyncSession) -> list[Schedule]:
    return list((await session.scalars(select(Schedule).order_by(Schedule.name))).all())


async def get_schedule_or_404(session: AsyncSession, schedule_id: uuid.UUID) -> Schedule:
    schedule = await session.get(Schedule, schedule_id)
    if not schedule:
        raise ApiProblem(
            status=404,
            code="SCHEDULE_NOT_FOUND",
            title="Schedule not found",
            detail=f"No schedule exists with id {schedule_id}.",
        )
    return schedule


async def write_schedule(
    session: AsyncSession,
    *,
    payload: ScheduleWrite,
    schedule_id: uuid.UUID | None = None,
) -> Schedule:
    _validated_payload(payload.task_type, payload.payload)
    next_run_at = next_schedule_run(payload.cron_expression, payload.timezone)
    schedule = (
        await get_schedule_or_404(session, schedule_id)
        if schedule_id
        else Schedule(name=payload.name, task_type=payload.task_type, next_run_at=next_run_at)
    )
    schedule.name = payload.name.strip()
    schedule.task_type = payload.task_type
    schedule.cron_expression = payload.cron_expression.strip()
    schedule.timezone = payload.timezone
    schedule.enabled = payload.enabled
    schedule.payload = payload.payload
    schedule.next_run_at = next_run_at
    session.add(schedule)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="SCHEDULE_NAME_CONFLICT",
            title="Schedule name already exists",
            detail=f"A schedule already uses {payload.name.strip()}.",
        ) from exc
    await session.refresh(schedule)
    return schedule


async def delete_schedule(session: AsyncSession, schedule_id: uuid.UUID) -> None:
    schedule = await get_schedule_or_404(session, schedule_id)
    await session.delete(schedule)
    await session.commit()


async def run_due_schedules(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 20,
) -> int:
    current = now or datetime.now(UTC)
    statement = (
        select(Schedule)
        .where(Schedule.enabled.is_(True), Schedule.next_run_at <= current)
        .order_by(Schedule.next_run_at, Schedule.id)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    schedules = list((await session.scalars(statement)).all())
    for schedule in schedules:
        job_payload = _validated_payload(schedule.task_type, schedule.payload)
        idempotency_key = f"schedule:{schedule.id}:{schedule.next_run_at.isoformat()}"
        if isinstance(job_payload, TokenRefreshJobCreate):
            job = await create_token_refresh_job(
                session,
                account_ids=job_payload.account_ids,
                failed_only=job_payload.failed_only,
                limit=job_payload.limit,
                idempotency_key=idempotency_key,
                commit=False,
            )
        elif isinstance(job_payload, RetentionSyncJobCreate):
            job = await create_retention_sync_job(
                session,
                account_ids=job_payload.account_ids,
                limit=job_payload.limit,
                idempotency_key=idempotency_key,
                commit=False,
            )
        else:
            job = await create_forwarding_job(
                session,
                account_ids=job_payload.account_ids,
                limit=job_payload.limit,
                idempotency_key=idempotency_key,
                commit=False,
            )
        schedule.last_run_at = current
        schedule.last_job_id = job.id
        schedule.next_run_at = next_schedule_run(
            schedule.cron_expression,
            schedule.timezone,
            after=current,
        )
    if schedules:
        await session.commit()
    else:
        await session.rollback()
    return len(schedules)
