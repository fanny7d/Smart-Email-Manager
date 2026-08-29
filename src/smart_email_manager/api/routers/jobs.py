from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import StreamingResponse

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.jobs import (
    CreateHealthCheckJob,
    JobEventsPage,
    JobRead,
)
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.services.jobs import (
    create_health_check_job,
    get_job_or_404,
    list_job_events,
    list_jobs,
    request_job_cancel,
    request_job_pause,
    resume_job,
)

router = APIRouter(tags=["jobs"])
JobsRead = Annotated[object, Depends(require_scopes("jobs:read"))]
JobsWrite = Annotated[object, Depends(require_scopes("jobs:write"))]


@router.get(
    "/jobs",
    operation_id="list_jobs",
    response_model=list[JobRead],
    summary="List recent persistent jobs",
)
async def get_jobs(
    session: SessionDependency,
    _auth: JobsRead,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[JobRead]:
    return [
        JobRead.model_validate(row) for row in await list_jobs(session, limit=limit, status=status_filter)
    ]


@router.post(
    "/health-check-jobs",
    operation_id="create_health_check_job",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a persistent account health-check job",
)
async def create_health_check(
    payload: CreateHealthCheckJob,
    session: SessionDependency,
    _auth: JobsWrite,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=160)] = None,
) -> JobRead:
    job = await create_health_check_job(
        session,
        account_ids=payload.account_ids,
        limit=payload.limit,
        mode=payload.mode,
        idempotency_key=idempotency_key,
    )
    return JobRead.model_validate(job)


@router.get(
    "/jobs/{job_id}",
    operation_id="get_job",
    response_model=JobRead,
    summary="Read persistent job state",
)
async def get_job(job_id: uuid.UUID, session: SessionDependency, _auth: JobsRead) -> JobRead:
    return JobRead.model_validate(await get_job_or_404(session, job_id))


@router.get(
    "/jobs/{job_id}/events",
    operation_id="list_job_events",
    response_model=JobEventsPage,
    summary="List persistent job events",
)
async def get_job_events(
    job_id: uuid.UUID,
    session: SessionDependency,
    _auth: JobsRead,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> JobEventsPage:
    events = await list_job_events(session, job_id, after_sequence=after_sequence, limit=limit)
    return JobEventsPage(
        items=events,
        next_sequence=events[-1].sequence if events else None,
    )


@router.get(
    "/jobs/{job_id}/events/stream",
    operation_id="stream_job_events",
    response_class=StreamingResponse,
    summary="Stream persistent job events as SSE",
)
async def stream_job_events(
    job_id: uuid.UUID,
    session: SessionDependency,
    _auth: JobsRead,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    await get_job_or_404(session, job_id)

    async def generate() -> AsyncIterator[str]:
        sequence = after_sequence
        while True:
            async with get_session_factory()() as event_session:
                events = await list_job_events(event_session, job_id, after_sequence=sequence, limit=200)
                job = await get_job_or_404(event_session, job_id)
            for event in events:
                sequence = event.sequence
                payload = json.dumps(
                    {
                        "sequence": event.sequence,
                        "type": event.event_type,
                        "level": event.level,
                        "message": event.message,
                        "data": event.data,
                        "created_at": event.created_at.isoformat(),
                    },
                    ensure_ascii=False,
                )
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"
            if job.status in {"completed", "partial", "failed", "cancelled"} and not events:
                break
            yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post(
    "/jobs/{job_id}/cancel",
    operation_id="cancel_job",
    response_model=JobRead,
    summary="Request cancellation of a persistent job",
)
async def cancel_job(
    job_id: uuid.UUID,
    session: SessionDependency,
    _auth: JobsWrite,
    response: Response,
) -> JobRead:
    response.status_code = status.HTTP_202_ACCEPTED
    return JobRead.model_validate(await request_job_cancel(session, job_id))


@router.post(
    "/jobs/{job_id}/pause",
    operation_id="pause_job",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def pause_job(
    job_id: uuid.UUID,
    session: SessionDependency,
    _auth: JobsWrite,
) -> JobRead:
    return JobRead.model_validate(await request_job_pause(session, job_id))


@router.post(
    "/jobs/{job_id}/resume",
    operation_id="resume_job",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_resume_job(
    job_id: uuid.UUID,
    session: SessionDependency,
    _auth: JobsWrite,
) -> JobRead:
    return JobRead.model_validate(await resume_job(session, job_id))
