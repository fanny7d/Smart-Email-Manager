from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.shares import (
    EmailShareCreate,
    EmailShareCreated,
    EmailShareRead,
    PublicEmailShareStatus,
)
from smart_email_manager.db.models import Account, EmailShareLink
from smart_email_manager.services.audit import add_audit_log


def _hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def share_status(link: EmailShareLink, *, now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    if link.revoked_at:
        return "revoked"
    if not link.never_expires and (not link.expires_at or link.expires_at <= current):
        return "expired"
    return "active"


def serialize_share(link: EmailShareLink) -> EmailShareRead:
    return EmailShareRead.model_validate(
        {
            **{field: getattr(link, field) for field in EmailShareRead.model_fields if field != "status"},
            "status": share_status(link),
        }
    )


async def create_email_share(
    session: AsyncSession,
    payload: EmailShareCreate,
) -> EmailShareCreated:
    account = await session.get(Account, payload.account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {payload.account_id}.",
        )
    token = f"sem_share_{secrets.token_urlsafe(32)}"
    now = datetime.now(UTC)
    link = EmailShareLink(
        account_id=account.id,
        token_prefix=token[:12],
        token_hash=_hash_token(token),
        allowed_folders=list(dict.fromkeys(payload.allowed_folders)),
        expires_at=None if payload.never_expires else now + timedelta(minutes=payload.duration_minutes),
        never_expires=payload.never_expires,
    )
    session.add(link)
    add_audit_log(
        session,
        action="email_share.create",
        resource_type="account",
        resource_id=str(account.id),
        data={"allowed_folders": link.allowed_folders},
    )
    await session.commit()
    await session.refresh(link)
    serialized = serialize_share(link)
    return EmailShareCreated(
        **serialized.model_dump(),
        token=token,
        share_path=f"/shared/mail/{token}",
    )


async def list_email_shares(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | None,
) -> list[EmailShareRead]:
    statement = select(EmailShareLink).order_by(EmailShareLink.created_at.desc())
    if account_id:
        statement = statement.where(EmailShareLink.account_id == account_id)
    return [serialize_share(row) for row in (await session.scalars(statement)).all()]


async def revoke_email_share(session: AsyncSession, share_id: uuid.UUID) -> EmailShareRead:
    link = await session.get(EmailShareLink, share_id, with_for_update=True)
    if not link:
        raise ApiProblem(
            status=404,
            code="EMAIL_SHARE_NOT_FOUND",
            title="Email share not found",
            detail=f"No email share exists with id {share_id}.",
        )
    link.revoked_at = link.revoked_at or datetime.now(UTC)
    add_audit_log(
        session,
        action="email_share.revoke",
        resource_type="email_share",
        resource_id=str(link.id),
    )
    await session.commit()
    await session.refresh(link)
    return serialize_share(link)


async def delete_email_share(session: AsyncSession, share_id: uuid.UUID) -> None:
    link = await session.get(EmailShareLink, share_id)
    if not link:
        raise ApiProblem(
            status=404,
            code="EMAIL_SHARE_NOT_FOUND",
            title="Email share not found",
            detail=f"No email share exists with id {share_id}.",
        )
    add_audit_log(
        session,
        action="email_share.delete",
        resource_type="email_share",
        resource_id=str(link.id),
    )
    await session.delete(link)
    await session.commit()


async def resolve_email_share(
    session: AsyncSession,
    token: str,
    *,
    folder: str | None = None,
) -> tuple[EmailShareLink, Account]:
    link = await session.scalar(
        select(EmailShareLink).where(EmailShareLink.token_hash == _hash_token(token.strip()))
    )
    if not link:
        raise ApiProblem(
            status=404,
            code="EMAIL_SHARE_INVALID",
            title="Email share is invalid",
            detail="The email share token is invalid.",
        )
    status = share_status(link)
    if status != "active":
        raise ApiProblem(
            status=410,
            code=f"EMAIL_SHARE_{status.upper()}",
            title=f"Email share is {status}",
            detail=f"The email share is {status}.",
        )
    if folder and folder not in link.allowed_folders:
        raise ApiProblem(
            status=403,
            code="EMAIL_SHARE_FOLDER_FORBIDDEN",
            title="Folder is not shared",
            detail="This email share does not grant access to the requested folder.",
        )
    account = await session.get(Account, link.account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="EMAIL_SHARE_INVALID",
            title="Email share is invalid",
            detail="The shared mailbox no longer exists.",
        )
    now = datetime.now(UTC)
    if not link.last_accessed_at or link.last_accessed_at <= now - timedelta(minutes=5):
        link.last_accessed_at = now
        await session.commit()
    return link, account


async def get_public_share_status(
    session: AsyncSession,
    token: str,
) -> PublicEmailShareStatus:
    link, account = await resolve_email_share(session, token)
    return PublicEmailShareStatus(
        status="active",
        account_id=account.id,
        email=account.email,
        allowed_folders=link.allowed_folders,
        expires_at=link.expires_at,
    )
