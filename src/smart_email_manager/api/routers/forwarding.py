from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.forwarding import (
    AccountForwardingRead,
    AccountForwardingWrite,
    ForwardingCursorWrite,
    ForwardingDeliveryRead,
    ForwardingDestinationRead,
    ForwardingDestinationWrite,
    ForwardingJobCreate,
    ForwardingTestResult,
)
from smart_email_manager.api.schemas.jobs import JobRead
from smart_email_manager.config import get_settings
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.forwarding import (
    delete_forwarding_destination,
    get_account_forwarding,
    list_forwarding_deliveries,
    list_forwarding_destinations,
    reset_forwarding_cursor,
    test_forwarding_destination,
    write_account_forwarding,
    write_forwarding_destination,
)
from smart_email_manager.services.jobs import create_forwarding_job

router = APIRouter(prefix="/forwarding", tags=["forwarding"])
ForwardRead = Annotated[object, Depends(require_scopes("forwarding:read"))]
ForwardWrite = Annotated[object, Depends(require_scopes("forwarding:write"))]


def _cipher() -> AccountSecretCipher:
    return AccountSecretCipher.from_settings(get_settings())


@router.get(
    "/destinations",
    operation_id="list_forwarding_destinations",
    response_model=list[ForwardingDestinationRead],
)
async def get_destinations(
    session: SessionDependency,
    _auth: ForwardRead,
) -> list[ForwardingDestinationRead]:
    return await list_forwarding_destinations(session)


@router.post(
    "/destinations",
    operation_id="create_forwarding_destination",
    response_model=ForwardingDestinationRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_destination(
    payload: ForwardingDestinationWrite,
    session: SessionDependency,
    _auth: ForwardWrite,
) -> ForwardingDestinationRead:
    return await write_forwarding_destination(session, payload=payload, cipher=_cipher())


@router.put(
    "/destinations/{destination_id}",
    operation_id="update_forwarding_destination",
    response_model=ForwardingDestinationRead,
)
async def put_destination(
    destination_id: uuid.UUID,
    payload: ForwardingDestinationWrite,
    session: SessionDependency,
    _auth: ForwardWrite,
) -> ForwardingDestinationRead:
    return await write_forwarding_destination(
        session,
        payload=payload,
        cipher=_cipher(),
        destination_id=destination_id,
    )


@router.post(
    "/destinations/{destination_id}/test",
    operation_id="test_forwarding_destination",
    response_model=ForwardingTestResult,
)
async def post_destination_test(
    destination_id: uuid.UUID,
    session: SessionDependency,
    _auth: ForwardWrite,
) -> ForwardingTestResult:
    return await test_forwarding_destination(session, destination_id, _cipher())


@router.delete(
    "/destinations/{destination_id}",
    operation_id="delete_forwarding_destination",
    status_code=204,
)
async def remove_destination(
    destination_id: uuid.UUID,
    session: SessionDependency,
    _auth: ForwardWrite,
) -> Response:
    await delete_forwarding_destination(session, destination_id)
    return Response(status_code=204)


@router.get(
    "/accounts/{account_id}",
    operation_id="get_account_forwarding",
    response_model=AccountForwardingRead,
)
async def get_account_config(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: ForwardRead,
) -> AccountForwardingRead:
    return await get_account_forwarding(session, account_id)


@router.put(
    "/accounts/{account_id}",
    operation_id="write_account_forwarding",
    response_model=AccountForwardingRead,
)
async def put_account_config(
    account_id: uuid.UUID,
    payload: AccountForwardingWrite,
    session: SessionDependency,
    _auth: ForwardWrite,
) -> AccountForwardingRead:
    return await write_account_forwarding(session, account_id=account_id, payload=payload)


@router.put(
    "/accounts/{account_id}/cursor",
    operation_id="reset_forwarding_cursor",
    response_model=AccountForwardingRead,
)
async def put_cursor(
    account_id: uuid.UUID,
    payload: ForwardingCursorWrite,
    session: SessionDependency,
    _auth: ForwardWrite,
) -> AccountForwardingRead:
    return await reset_forwarding_cursor(session, account_id, payload.cursor_at)


@router.post(
    "/jobs",
    operation_id="create_forwarding_job",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_job(
    payload: ForwardingJobCreate,
    session: SessionDependency,
    _auth: ForwardWrite,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=160)] = None,
) -> JobRead:
    return JobRead.model_validate(
        await create_forwarding_job(
            session,
            account_ids=payload.account_ids,
            limit=payload.limit,
            idempotency_key=idempotency_key,
        )
    )


@router.get(
    "/deliveries",
    operation_id="list_forwarding_deliveries",
    response_model=list[ForwardingDeliveryRead],
)
async def get_deliveries(
    session: SessionDependency,
    _auth: ForwardRead,
    account_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ForwardingDeliveryRead]:
    return await list_forwarding_deliveries(session, account_id=account_id, limit=limit)
