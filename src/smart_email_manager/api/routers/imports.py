from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.imports import (
    ImportBatchCreate,
    ImportBatchDetail,
    ImportBatchRead,
)
from smart_email_manager.config import get_settings
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.imports import (
    commit_import_batch,
    create_import_batch,
    get_import_batch,
    list_import_batches,
    rollback_import_batch,
)

router = APIRouter(prefix="/import-batches", tags=["imports"])
ImportsRead = Annotated[object, Depends(require_scopes("imports:read"))]
ImportsWrite = Annotated[object, Depends(require_scopes("imports:write"))]


@router.post(
    "",
    operation_id="create_import_batch",
    response_model=ImportBatchDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Parse and encrypt an import batch without writing accounts",
)
async def post_import_batch(
    payload: ImportBatchCreate,
    session: SessionDependency,
    _auth: ImportsWrite,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=160)] = None,
) -> ImportBatchDetail:
    batch = await create_import_batch(
        session,
        payload=payload,
        cipher=AccountSecretCipher.from_settings(get_settings()),
        idempotency_key=idempotency_key,
    )
    return ImportBatchDetail.model_validate(batch)


@router.get(
    "",
    operation_id="list_import_batches",
    response_model=list[ImportBatchRead],
    summary="List import batches",
)
async def get_import_batches(
    session: SessionDependency,
    _auth: ImportsRead,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ImportBatchRead]:
    return [ImportBatchRead.model_validate(row) for row in await list_import_batches(session, limit)]


@router.get(
    "/{batch_id}",
    operation_id="get_import_batch",
    response_model=ImportBatchDetail,
    summary="Read import preflight and item results",
)
async def get_import_batch_route(
    batch_id: uuid.UUID,
    session: SessionDependency,
    _auth: ImportsRead,
) -> ImportBatchDetail:
    return ImportBatchDetail.model_validate(await get_import_batch(session, batch_id))


@router.post(
    "/{batch_id}/commit",
    operation_id="commit_import_batch",
    response_model=ImportBatchDetail,
    summary="Commit valid import items to accounts",
)
async def commit_import_batch_route(
    batch_id: uuid.UUID,
    session: SessionDependency,
    _auth: ImportsWrite,
) -> ImportBatchDetail:
    return ImportBatchDetail.model_validate(
        await commit_import_batch(
            session,
            batch_id=batch_id,
            cipher=AccountSecretCipher.from_settings(get_settings()),
        )
    )


@router.post(
    "/{batch_id}/rollback",
    operation_id="rollback_import_batch",
    response_model=ImportBatchDetail,
    summary="Guardedly remove unchanged accounts created by an import batch",
)
async def rollback_import_batch_route(
    batch_id: uuid.UUID,
    session: SessionDependency,
    _auth: ImportsWrite,
) -> ImportBatchDetail:
    return ImportBatchDetail.model_validate(await rollback_import_batch(session, batch_id))
