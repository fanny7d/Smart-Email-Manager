import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.fleet import FleetSummary
from smart_email_manager.api.schemas.views import (
    AccountViewsRead,
    SavedAccountViewCreate,
    SavedAccountViewRead,
    SavedAccountViewUpdate,
)
from smart_email_manager.services.fleet import get_fleet_summary
from smart_email_manager.services.views import (
    builtin_account_views,
    create_saved_account_view,
    delete_saved_account_view,
    list_saved_account_views,
    update_saved_account_view,
)

router = APIRouter(prefix="/fleet", tags=["fleet"])
FleetRead = Annotated[object, Depends(require_scopes("fleet:read"))]
FleetWrite = Annotated[object, Depends(require_scopes("fleet:write"))]


@router.get(
    "/summary",
    operation_id="get_fleet_summary",
    response_model=FleetSummary,
    summary="Summarize mailbox fleet health",
)
async def fleet_summary(session: SessionDependency, _auth: FleetRead) -> FleetSummary:
    return await get_fleet_summary(session)


@router.get(
    "/views",
    operation_id="list_account_views",
    response_model=AccountViewsRead,
    summary="List built-in smart views and user-saved account filters",
)
async def account_views(session: SessionDependency, _auth: FleetRead) -> AccountViewsRead:
    return AccountViewsRead(
        builtin=builtin_account_views(),
        saved=[
            SavedAccountViewRead.model_validate(row)
            for row in await list_saved_account_views(session)
        ],
    )


@router.post(
    "/views",
    operation_id="create_saved_account_view",
    response_model=SavedAccountViewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_account_view(
    payload: SavedAccountViewCreate,
    session: SessionDependency,
    _auth: FleetWrite,
) -> SavedAccountViewRead:
    return SavedAccountViewRead.model_validate(await create_saved_account_view(session, payload))


@router.put(
    "/views/{view_id}",
    operation_id="update_saved_account_view",
    response_model=SavedAccountViewRead,
)
async def update_account_view(
    view_id: uuid.UUID,
    payload: SavedAccountViewUpdate,
    session: SessionDependency,
    _auth: FleetWrite,
) -> SavedAccountViewRead:
    return SavedAccountViewRead.model_validate(
        await update_saved_account_view(session, view_id, payload)
    )


@router.delete(
    "/views/{view_id}",
    operation_id="delete_saved_account_view",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account_view(
    view_id: uuid.UUID,
    session: SessionDependency,
    _auth: FleetWrite,
) -> Response:
    await delete_saved_account_view(session, view_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
