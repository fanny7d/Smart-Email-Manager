from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.jobs import JobRead
from smart_email_manager.api.schemas.mail import MailDetailRead, MailPageRead
from smart_email_manager.api.schemas.retention import (
    RetentionPolicyRead,
    RetentionPolicyWrite,
    RetentionStatsRead,
    RetentionSyncJobCreate,
)
from smart_email_manager.services.jobs import create_retention_sync_job
from smart_email_manager.services.retention import (
    clear_retained_mail,
    get_retained_mail_detail,
    get_retention_policy_or_default,
    get_retention_stats,
    list_retained_mail,
    list_retention_policies,
    write_retention_policy,
)

router = APIRouter(prefix="/retention", tags=["mail retention"])
RetentionRead = Annotated[object, Depends(require_scopes("retention:read"))]
RetentionWrite = Annotated[object, Depends(require_scopes("retention:write"))]
Folder = Literal["inbox", "junkemail", "all"]


@router.get("/policies", operation_id="list_retention_policies", response_model=list[RetentionPolicyRead])
async def get_policies(
    session: SessionDependency,
    _auth: RetentionRead,
) -> list[RetentionPolicyRead]:
    return await list_retention_policies(session)


@router.get(
    "/accounts/{account_id}/policy",
    operation_id="get_retention_policy",
    response_model=RetentionPolicyRead,
)
async def get_policy(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: RetentionRead,
) -> RetentionPolicyRead:
    return RetentionPolicyRead.model_validate(await get_retention_policy_or_default(session, account_id))


@router.put(
    "/accounts/{account_id}/policy",
    operation_id="write_retention_policy",
    response_model=RetentionPolicyRead,
)
async def put_policy(
    account_id: uuid.UUID,
    payload: RetentionPolicyWrite,
    session: SessionDependency,
    _auth: RetentionWrite,
) -> RetentionPolicyRead:
    return await write_retention_policy(session, account_id=account_id, payload=payload)


@router.post(
    "/sync-jobs",
    operation_id="create_retention_sync_job",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_sync_job(
    payload: RetentionSyncJobCreate,
    session: SessionDependency,
    _auth: RetentionWrite,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=160)] = None,
) -> JobRead:
    return JobRead.model_validate(
        await create_retention_sync_job(
            session,
            account_ids=payload.account_ids,
            limit=payload.limit,
            idempotency_key=idempotency_key,
        )
    )


@router.get("/stats", operation_id="get_retention_stats", response_model=RetentionStatsRead)
async def get_stats(
    session: SessionDependency,
    _auth: RetentionRead,
) -> RetentionStatsRead:
    return await get_retention_stats(session)


@router.get(
    "/accounts/{account_id}/mail",
    operation_id="list_retained_mail",
    response_model=MailPageRead,
)
async def get_cached_mail(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: RetentionRead,
    folder: Folder = "inbox",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MailPageRead:
    return await list_retained_mail(
        session,
        account_id=account_id,
        folder=folder,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/accounts/{account_id}/mail/{message_id}",
    operation_id="get_retained_mail_detail",
    response_model=MailDetailRead,
)
async def get_cached_detail(
    account_id: uuid.UUID,
    message_id: str,
    session: SessionDependency,
    _auth: RetentionRead,
    folder: Literal["inbox", "junkemail"] = "inbox",
) -> MailDetailRead:
    return await get_retained_mail_detail(
        session,
        account_id=account_id,
        folder=folder,
        message_id=message_id,
    )


@router.delete("/cache", operation_id="clear_retained_mail", status_code=204)
async def delete_cache(
    session: SessionDependency,
    _auth: RetentionWrite,
    account_id: uuid.UUID | None = None,
) -> Response:
    await clear_retained_mail(session, account_id=account_id)
    return Response(status_code=204)
