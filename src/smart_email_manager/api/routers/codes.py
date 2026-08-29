from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.codes import (
    VerificationCodePage,
    VerificationCodeQuery,
)
from smart_email_manager.services.codes import (
    find_account_verification_codes,
    find_fleet_verification_codes,
)

router = APIRouter(tags=["verification codes"])
CodesRead = Annotated[object, Depends(require_scopes("mail:read"))]
Method = Literal["auto", "graph", "imap"]


@router.get(
    "/accounts/{account_id}/verification-codes",
    operation_id="list_account_verification_codes",
    response_model=VerificationCodePage,
)
async def get_account_codes(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: CodesRead,
    recent_minutes: Annotated[int, Query(ge=1, le=1_440)] = 30,
    messages_per_account: Annotated[int, Query(ge=1, le=100)] = 30,
    include_junk: bool = True,
    method: Method = "auto",
) -> VerificationCodePage:
    return await find_account_verification_codes(
        session,
        account_id,
        recent_minutes=recent_minutes,
        messages_per_account=messages_per_account,
        include_junk=include_junk,
        method=method,
    )


@router.post(
    "/verification-codes/query",
    operation_id="query_verification_codes",
    response_model=VerificationCodePage,
)
async def query_codes(
    payload: VerificationCodeQuery,
    session: SessionDependency,
    _auth: CodesRead,
) -> VerificationCodePage:
    return await find_fleet_verification_codes(
        session,
        account_ids=payload.account_ids,
        recent_minutes=payload.recent_minutes,
        messages_per_account=payload.messages_per_account,
        account_limit=payload.account_limit,
        include_junk=payload.include_junk,
        method=payload.method,
    )
