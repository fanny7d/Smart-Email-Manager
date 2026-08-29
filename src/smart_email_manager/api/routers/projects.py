from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.projects import (
    ProjectAccountRead,
    ProjectAccountsAction,
    ProjectAccountsActionResult,
    ProjectAccountsAdd,
    ProjectClaimRead,
    ProjectClaimRequest,
    ProjectCreate,
    ProjectEventRead,
    ProjectLeaseAction,
    ProjectLeaseHeartbeat,
    ProjectRead,
    ProjectStatusWrite,
)
from smart_email_manager.services.projects import (
    add_project_accounts,
    claim_project_account,
    create_project,
    finish_project_lease,
    heartbeat_project_lease,
    list_project_accounts,
    list_project_events,
    list_projects,
    mutate_project_accounts,
    set_project_status,
)

router = APIRouter(prefix="/projects", tags=["work projects"])
ProjectsRead = Annotated[object, Depends(require_scopes("projects:read"))]
ProjectsWrite = Annotated[object, Depends(require_scopes("projects:write"))]
ProjectsClaim = Annotated[object, Depends(require_scopes("projects:claim"))]


@router.get("", operation_id="list_work_projects", response_model=list[ProjectRead])
async def get_projects(
    session: SessionDependency,
    _auth: ProjectsRead,
) -> list[ProjectRead]:
    return await list_projects(session)


@router.post(
    "",
    operation_id="create_work_project",
    response_model=ProjectRead,
    status_code=201,
)
async def post_project(
    payload: ProjectCreate,
    session: SessionDependency,
    _auth: ProjectsWrite,
) -> ProjectRead:
    return await create_project(session, payload)


@router.put(
    "/{project_id}/status",
    operation_id="set_work_project_status",
    response_model=ProjectRead,
)
async def put_project_status(
    project_id: uuid.UUID,
    payload: ProjectStatusWrite,
    session: SessionDependency,
    _auth: ProjectsWrite,
) -> ProjectRead:
    return await set_project_status(session, project_id, payload.status)


@router.post(
    "/{project_id}/accounts",
    operation_id="add_work_project_accounts",
    response_model=ProjectRead,
)
async def post_project_accounts(
    project_id: uuid.UUID,
    payload: ProjectAccountsAdd,
    session: SessionDependency,
    _auth: ProjectsWrite,
) -> ProjectRead:
    return await add_project_accounts(session, project_id, payload)


@router.get(
    "/{project_id}/accounts",
    operation_id="list_work_project_accounts",
    response_model=list[ProjectAccountRead],
)
async def get_project_accounts(
    project_id: uuid.UUID,
    session: SessionDependency,
    _auth: ProjectsRead,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[ProjectAccountRead]:
    return await list_project_accounts(session, project_id, limit=limit)


@router.post(
    "/{project_id}/account-actions",
    operation_id="mutate_work_project_accounts",
    response_model=ProjectAccountsActionResult,
)
async def post_project_account_action(
    project_id: uuid.UUID,
    payload: ProjectAccountsAction,
    session: SessionDependency,
    _auth: ProjectsWrite,
) -> ProjectAccountsActionResult:
    return await mutate_project_accounts(session, project_id, payload)


@router.post(
    "/{project_id}/claims",
    operation_id="claim_work_project_account",
    response_model=ProjectClaimRead,
)
async def post_claim(
    project_id: uuid.UUID,
    payload: ProjectClaimRequest,
    session: SessionDependency,
    _auth: ProjectsClaim,
) -> ProjectClaimRead:
    return await claim_project_account(session, project_id, payload)


@router.post(
    "/leases/{project_account_id}/heartbeat",
    operation_id="heartbeat_work_project_lease",
    response_model=ProjectAccountRead,
)
async def post_heartbeat(
    project_account_id: uuid.UUID,
    payload: ProjectLeaseHeartbeat,
    session: SessionDependency,
    _auth: ProjectsClaim,
) -> ProjectAccountRead:
    return await heartbeat_project_lease(session, project_account_id, payload)


@router.post(
    "/leases/{project_account_id}/complete",
    operation_id="complete_work_project_lease",
    response_model=ProjectAccountRead,
)
async def post_complete(
    project_account_id: uuid.UUID,
    payload: ProjectLeaseAction,
    session: SessionDependency,
    _auth: ProjectsClaim,
) -> ProjectAccountRead:
    return await finish_project_lease(session, project_account_id, payload, status="done")


@router.post(
    "/leases/{project_account_id}/fail",
    operation_id="fail_work_project_lease",
    response_model=ProjectAccountRead,
)
async def post_fail(
    project_account_id: uuid.UUID,
    payload: ProjectLeaseAction,
    session: SessionDependency,
    _auth: ProjectsClaim,
) -> ProjectAccountRead:
    return await finish_project_lease(session, project_account_id, payload, status="failed")


@router.post(
    "/leases/{project_account_id}/release",
    operation_id="release_work_project_lease",
    response_model=ProjectAccountRead,
)
async def post_release(
    project_account_id: uuid.UUID,
    payload: ProjectLeaseAction,
    session: SessionDependency,
    _auth: ProjectsClaim,
) -> ProjectAccountRead:
    return await finish_project_lease(session, project_account_id, payload, status="to_claim")


@router.get(
    "/{project_id}/events",
    operation_id="list_work_project_events",
    response_model=list[ProjectEventRead],
)
async def get_project_events(
    project_id: uuid.UUID,
    session: SessionDependency,
    _auth: ProjectsRead,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[ProjectEventRead]:
    return await list_project_events(session, project_id, after=after, limit=limit)
