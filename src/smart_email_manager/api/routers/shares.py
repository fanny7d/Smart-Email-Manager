from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.mail import MailDetailRead, MailPageRead
from smart_email_manager.api.schemas.shares import (
    EmailShareCreate,
    EmailShareCreated,
    EmailShareRead,
    PublicEmailShareStatus,
)
from smart_email_manager.services.mail import get_mail_detail, list_mail
from smart_email_manager.services.retention import (
    get_retained_mail_detail,
    list_retained_mail,
)
from smart_email_manager.services.shares import (
    create_email_share,
    delete_email_share,
    get_public_share_status,
    list_email_shares,
    resolve_email_share,
    revoke_email_share,
)

router = APIRouter(tags=["email shares"])
ShareRead = Annotated[object, Depends(require_scopes("shares:read"))]
ShareWrite = Annotated[object, Depends(require_scopes("shares:write"))]
Folder = Literal["inbox", "junkemail"]
Source = Literal["auto", "live", "retained"]


@router.post(
    "/email-shares",
    operation_id="create_email_share",
    response_model=EmailShareCreated,
    status_code=status.HTTP_201_CREATED,
)
async def post_share(
    payload: EmailShareCreate,
    session: SessionDependency,
    _auth: ShareWrite,
) -> EmailShareCreated:
    return await create_email_share(session, payload)


@router.get(
    "/email-shares",
    operation_id="list_email_shares",
    response_model=list[EmailShareRead],
)
async def get_shares(
    session: SessionDependency,
    _auth: ShareRead,
    account_id: uuid.UUID | None = None,
) -> list[EmailShareRead]:
    return await list_email_shares(session, account_id=account_id)


@router.post(
    "/email-shares/{share_id}/revoke",
    operation_id="revoke_email_share",
    response_model=EmailShareRead,
)
async def post_revoke(
    share_id: uuid.UUID,
    session: SessionDependency,
    _auth: ShareWrite,
) -> EmailShareRead:
    return await revoke_email_share(session, share_id)


@router.delete("/email-shares/{share_id}", operation_id="delete_email_share", status_code=204)
async def remove_share(
    share_id: uuid.UUID,
    session: SessionDependency,
    _auth: ShareWrite,
) -> Response:
    await delete_email_share(session, share_id)
    return Response(status_code=204)


@router.get(
    "/public/email-shares/{token}/status",
    operation_id="get_public_email_share_status",
    response_model=PublicEmailShareStatus,
)
async def public_status(token: str, session: SessionDependency) -> PublicEmailShareStatus:
    return await get_public_share_status(session, token)


@router.get(
    "/public/email-shares/{token}/mail",
    operation_id="list_public_email_share_mail",
    response_model=MailPageRead,
)
async def public_mail(
    token: str,
    session: SessionDependency,
    folder: Folder = "inbox",
    source: Source = "auto",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MailPageRead:
    _link, account = await resolve_email_share(session, token, folder=folder)
    if source == "retained":
        return await list_retained_mail(
            session,
            account_id=account.id,
            folder=folder,
            offset=offset,
            limit=limit,
        )
    try:
        return await list_mail(
            session,
            account.id,
            folder=folder,
            offset=offset,
            limit=limit,
            method="auto",
        )
    except ApiProblem:
        if source == "live":
            raise
        return await list_retained_mail(
            session,
            account_id=account.id,
            folder=folder,
            offset=offset,
            limit=limit,
        )


@router.get(
    "/public/email-shares/{token}/mail/{message_id}",
    operation_id="get_public_email_share_mail_detail",
    response_model=MailDetailRead,
)
async def public_mail_detail(
    token: str,
    message_id: str,
    session: SessionDependency,
    folder: Folder = "inbox",
    source: Source = "auto",
) -> MailDetailRead:
    _link, account = await resolve_email_share(session, token, folder=folder)
    if source == "retained":
        return await get_retained_mail_detail(
            session,
            account_id=account.id,
            folder=folder,
            message_id=message_id,
        )
    try:
        return await get_mail_detail(
            session,
            account.id,
            folder=folder,
            message_id=message_id,
            method="auto",
        )
    except ApiProblem:
        if source == "live":
            raise
        return await get_retained_mail_detail(
            session,
            account_id=account.id,
            folder=folder,
            message_id=message_id,
        )
