from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.auth import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from smart_email_manager.db.models import ApiToken
from smart_email_manager.security.tokens import create_persistent_token, revoke_persistent_token

router = APIRouter(prefix="/auth/tokens", tags=["auth"])
ManageTokens = Annotated[object, Depends(require_scopes("tokens:manage"))]


@router.post(
    "",
    operation_id="create_api_token",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API token and return its secret once",
)
async def create_api_token(
    payload: ApiTokenCreate,
    session: SessionDependency,
    _auth: ManageTokens,
) -> ApiTokenCreated:
    row, secret = await create_persistent_token(
        session,
        name=payload.name,
        scopes=payload.scopes,
        expires_in_days=payload.expires_in_days,
    )
    return ApiTokenCreated(token=ApiTokenRead.model_validate(row), secret=secret)


@router.get(
    "",
    operation_id="list_api_tokens",
    response_model=list[ApiTokenRead],
    summary="List API token metadata",
)
async def list_api_tokens(session: SessionDependency, _auth: ManageTokens) -> list[ApiTokenRead]:
    rows = list((await session.scalars(select(ApiToken).order_by(ApiToken.created_at.desc()))).all())
    return [ApiTokenRead.model_validate(row) for row in rows]


@router.post(
    "/{token_id}/revoke",
    operation_id="revoke_api_token",
    response_model=ApiTokenRead,
    summary="Revoke an API token",
)
async def revoke_api_token(
    token_id: uuid.UUID,
    session: SessionDependency,
    _auth: ManageTokens,
) -> ApiTokenRead:
    return ApiTokenRead.model_validate(await revoke_persistent_token(session, token_id))
