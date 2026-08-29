from __future__ import annotations

import re
import uuid
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.mail import MailDetailRead, MailPageRead
from smart_email_manager.services.mail import (
    delete_mail,
    download_mail_attachment,
    get_mail_detail,
    get_raw_mail,
    list_mail,
    mark_mail_read,
)

router = APIRouter(prefix="/accounts/{account_id}/mail", tags=["mail"])
MailRead = Annotated[object, Depends(require_scopes("mail:read"))]
MailWrite = Annotated[object, Depends(require_scopes("mail:write"))]
Folder = Literal["inbox", "junkemail", "deleteditems", "all"]
Method = Literal["auto", "graph", "imap"]


@router.get("", operation_id="list_mail", response_model=MailPageRead)
async def get_mail(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: MailRead,
    folder: Folder = "inbox",
    method: Method = "auto",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MailPageRead:
    return await list_mail(
        session,
        account_id,
        folder=folder,
        method=method,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/messages/{message_id}",
    operation_id="get_mail_detail",
    response_model=MailDetailRead,
)
async def get_message(
    account_id: uuid.UUID,
    message_id: str,
    session: SessionDependency,
    _auth: MailRead,
    folder: ExcludeAllFolder = "inbox",
    method: Method = "auto",
) -> MailDetailRead:
    return await get_mail_detail(
        session,
        account_id,
        folder=folder,
        message_id=message_id,
        method=method,
    )


ExcludeAllFolder = Literal["inbox", "junkemail", "deleteditems"]


@router.get("/messages/{message_id}/raw", operation_id="get_raw_mail")
async def get_raw_message(
    account_id: uuid.UUID,
    message_id: str,
    session: SessionDependency,
    _auth: MailRead,
    folder: ExcludeAllFolder = "inbox",
    method: Method = "auto",
) -> Response:
    raw = await get_raw_mail(
        session,
        account_id,
        folder=folder,
        message_id=message_id,
        method=method,
    )
    return Response(
        content=raw,
        media_type="message/rfc822",
        headers={"Content-Disposition": 'attachment; filename="message.eml"'},
    )


@router.get(
    "/messages/{message_id}/attachments/{attachment_id}",
    operation_id="download_mail_attachment",
)
async def get_attachment(
    account_id: uuid.UUID,
    message_id: str,
    attachment_id: str,
    session: SessionDependency,
    _auth: MailRead,
    folder: ExcludeAllFolder = "inbox",
    method: Method = "auto",
) -> Response:
    attachment = await download_mail_attachment(
        session,
        account_id,
        folder=folder,
        message_id=message_id,
        attachment_id=attachment_id,
        method=method,
    )
    filename = re.sub(r"[\r\n\\/]+", "_", attachment.name).strip() or "attachment"
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/messages/{message_id}/read", operation_id="mark_mail_read", status_code=204)
async def post_mark_read(
    account_id: uuid.UUID,
    message_id: str,
    session: SessionDependency,
    _auth: MailWrite,
    folder: ExcludeAllFolder = "inbox",
    method: Method = "auto",
) -> Response:
    await mark_mail_read(
        session,
        account_id,
        folder=folder,
        message_id=message_id,
        method=method,
    )
    return Response(status_code=204)


@router.delete("/messages/{message_id}", operation_id="delete_mail", status_code=204)
async def remove_message(
    account_id: uuid.UUID,
    message_id: str,
    session: SessionDependency,
    _auth: MailWrite,
    folder: ExcludeAllFolder = "inbox",
    method: Method = "auto",
) -> Response:
    await delete_mail(
        session,
        account_id,
        folder=folder,
        message_id=message_id,
        method=method,
    )
    return Response(status_code=204)
