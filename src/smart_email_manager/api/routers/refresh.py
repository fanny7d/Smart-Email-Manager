from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.jobs import JobRead
from smart_email_manager.api.schemas.refresh import (
    ScheduleRead,
    ScheduleWrite,
    TokenRefreshJobCreate,
    TokenRefreshLogRead,
    TokenRefreshSummary,
)
from smart_email_manager.services.jobs import create_token_refresh_job
from smart_email_manager.services.refresh import (
    get_token_refresh_summary,
    list_token_refresh_logs,
)
from smart_email_manager.services.schedules import (
    delete_schedule,
    list_schedules,
    write_schedule,
)

router = APIRouter(tags=["token refresh and schedules"])
RefreshRead = Annotated[object, Depends(require_scopes("refresh:read"))]
RefreshWrite = Annotated[object, Depends(require_scopes("refresh:write"))]
SchedulesRead = Annotated[object, Depends(require_scopes("schedules:read"))]
SchedulesWrite = Annotated[object, Depends(require_scopes("schedules:write"))]


@router.post(
    "/token-refresh-jobs",
    operation_id="create_token_refresh_job",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create a persistent OAuth token refresh job",
)
async def post_token_refresh_job(
    payload: TokenRefreshJobCreate,
    session: SessionDependency,
    _auth: RefreshWrite,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=160)] = None,
) -> JobRead:
    job = await create_token_refresh_job(
        session,
        account_ids=payload.account_ids,
        failed_only=payload.failed_only,
        limit=payload.limit,
        idempotency_key=idempotency_key,
    )
    return JobRead.model_validate(job)


@router.get(
    "/token-refresh-logs",
    operation_id="list_token_refresh_logs",
    response_model=list[TokenRefreshLogRead],
)
async def get_token_refresh_logs(
    session: SessionDependency,
    _auth: RefreshRead,
    account_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TokenRefreshLogRead]:
    return [
        TokenRefreshLogRead.model_validate(row)
        for row in await list_token_refresh_logs(session, account_id=account_id, limit=limit)
    ]


@router.get(
    "/token-refresh-summary",
    operation_id="get_token_refresh_summary",
    response_model=TokenRefreshSummary,
)
async def get_refresh_summary(
    session: SessionDependency,
    _auth: RefreshRead,
) -> TokenRefreshSummary:
    return await get_token_refresh_summary(session)


@router.get(
    "/schedules",
    operation_id="list_schedules",
    response_model=list[ScheduleRead],
)
async def get_schedules(
    session: SessionDependency,
    _auth: SchedulesRead,
) -> list[ScheduleRead]:
    return [ScheduleRead.model_validate(row) for row in await list_schedules(session)]


@router.post(
    "/schedules",
    operation_id="create_schedule",
    response_model=ScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_schedule(
    payload: ScheduleWrite,
    session: SessionDependency,
    _auth: SchedulesWrite,
) -> ScheduleRead:
    return ScheduleRead.model_validate(await write_schedule(session, payload=payload))


@router.put(
    "/schedules/{schedule_id}",
    operation_id="update_schedule",
    response_model=ScheduleRead,
)
async def put_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleWrite,
    session: SessionDependency,
    _auth: SchedulesWrite,
) -> ScheduleRead:
    return ScheduleRead.model_validate(
        await write_schedule(session, payload=payload, schedule_id=schedule_id)
    )


@router.delete(
    "/schedules/{schedule_id}",
    operation_id="delete_schedule",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_schedule(
    schedule_id: uuid.UUID,
    session: SessionDependency,
    _auth: SchedulesWrite,
) -> Response:
    await delete_schedule(session, schedule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
