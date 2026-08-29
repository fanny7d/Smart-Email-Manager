from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.mail import (
    MailAttachmentRead,
    MailDetailRead,
    MailPageRead,
    MailSummaryRead,
)
from smart_email_manager.api.schemas.retention import (
    RetentionPolicyRead,
    RetentionPolicyWrite,
    RetentionStatsRead,
)
from smart_email_manager.db.models import Account, RetainedMailMessage, RetentionPolicy
from smart_email_manager.services.mail import get_mail_detail, list_mail


async def get_retention_policy_or_default(
    session: AsyncSession,
    account_id: uuid.UUID,
) -> RetentionPolicy:
    if not await session.get(Account, account_id):
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    policy = await session.get(RetentionPolicy, account_id)
    if policy:
        return policy
    return RetentionPolicy(account_id=account_id)


async def list_retention_policies(session: AsyncSession) -> list[RetentionPolicyRead]:
    rows = list((await session.scalars(select(RetentionPolicy).order_by(RetentionPolicy.created_at))).all())
    return [RetentionPolicyRead.model_validate(row) for row in rows]


async def write_retention_policy(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    payload: RetentionPolicyWrite,
) -> RetentionPolicyRead:
    policy = await get_retention_policy_or_default(session, account_id)
    policy.enabled = payload.enabled
    policy.retain_bodies = payload.retain_bodies
    policy.folders = list(dict.fromkeys(payload.folders))
    policy.max_messages = payload.max_messages
    policy.max_age_days = payload.max_age_days
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return RetentionPolicyRead.model_validate(policy)


async def cache_mail_page(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    page: MailPageRead,
) -> int:
    now = datetime.now(UTC)
    for item in page.items:
        statement = insert(RetainedMailMessage).values(
            account_id=account_id,
            folder=item.folder,
            provider_message_id=item.id,
            id_mode=item.id_mode,
            subject=item.subject,
            sender=item.sender,
            recipients=item.recipients,
            received_at=item.received_at,
            is_read=item.is_read,
            has_attachments=item.has_attachments,
            body_preview=item.body_preview,
            last_synced_at=now,
        )
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_retained_mail_messages_account_id",
                set_={
                    "subject": statement.excluded.subject,
                    "sender": statement.excluded.sender,
                    "recipients": statement.excluded.recipients,
                    "received_at": statement.excluded.received_at,
                    "is_read": statement.excluded.is_read,
                    "has_attachments": statement.excluded.has_attachments,
                    "body_preview": statement.excluded.body_preview,
                    "last_synced_at": now,
                    "updated_at": now,
                },
            )
        )
    await session.commit()
    return len(page.items)


async def cache_mail_detail(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    detail: MailDetailRead,
) -> None:
    now = datetime.now(UTC)
    statement = insert(RetainedMailMessage).values(
        account_id=account_id,
        folder=detail.folder,
        provider_message_id=detail.id,
        id_mode=detail.id_mode,
        subject=detail.subject,
        sender=detail.sender,
        recipients=detail.recipients,
        cc=detail.cc,
        received_at=detail.received_at,
        is_read=detail.is_read,
        has_attachments=bool(detail.attachments),
        body=detail.body,
        body_type=detail.body_type,
        attachments=[item.model_dump() for item in detail.attachments],
        body_cached_at=now,
        last_synced_at=now,
    )
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_retained_mail_messages_account_id",
            set_={
                "subject": statement.excluded.subject,
                "sender": statement.excluded.sender,
                "recipients": statement.excluded.recipients,
                "cc": statement.excluded.cc,
                "received_at": statement.excluded.received_at,
                "is_read": statement.excluded.is_read,
                "has_attachments": statement.excluded.has_attachments,
                "body": statement.excluded.body,
                "body_type": statement.excluded.body_type,
                "attachments": statement.excluded.attachments,
                "body_cached_at": now,
                "last_synced_at": now,
                "updated_at": now,
            },
        )
    )
    await session.commit()


async def list_retained_mail(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    folder: str,
    offset: int,
    limit: int,
) -> MailPageRead:
    statement = select(RetainedMailMessage).where(RetainedMailMessage.account_id == account_id)
    if folder != "all":
        statement = statement.where(RetainedMailMessage.folder == folder)
    rows = list(
        (
            await session.scalars(
                statement.order_by(
                    RetainedMailMessage.received_at.desc(),
                    RetainedMailMessage.id.desc(),
                )
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    return MailPageRead(
        items=[
            MailSummaryRead(
                id=row.provider_message_id,
                folder=row.folder,
                subject=row.subject,
                sender=row.sender,
                recipients=row.recipients,
                received_at=row.received_at,
                is_read=row.is_read,
                has_attachments=row.has_attachments,
                body_preview=row.body_preview,
                id_mode=row.id_mode,
            )
            for row in rows[:limit]
        ],
        has_more=len(rows) > limit,
        method="retained",
    )


async def get_retained_mail_detail(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    folder: str,
    message_id: str,
) -> MailDetailRead:
    row = await session.scalar(
        select(RetainedMailMessage)
        .where(
            RetainedMailMessage.account_id == account_id,
            RetainedMailMessage.folder == folder,
            RetainedMailMessage.provider_message_id == message_id,
            RetainedMailMessage.body.is_not(None),
        )
        .order_by(RetainedMailMessage.updated_at.desc())
        .limit(1)
    )
    if not row:
        raise ApiProblem(
            status=404,
            code="RETAINED_MAIL_NOT_FOUND",
            title="Retained mail was not found",
            detail="The requested message body is not retained locally.",
        )
    return MailDetailRead(
        id=row.provider_message_id,
        folder=row.folder,
        subject=row.subject,
        sender=row.sender,
        recipients=row.recipients,
        cc=row.cc,
        received_at=row.received_at,
        is_read=row.is_read,
        body=row.body or "",
        body_type=row.body_type,
        attachments=[MailAttachmentRead.model_validate(item) for item in row.attachments],
        id_mode=row.id_mode,
        method="retained",
    )


async def prune_retained_mail(session: AsyncSession, policy: RetentionPolicy) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=policy.max_age_days)
    old_result = await session.execute(
        delete(RetainedMailMessage).where(
            RetainedMailMessage.account_id == policy.account_id,
            RetainedMailMessage.last_synced_at < cutoff,
        )
    )
    retained_ids = (
        select(RetainedMailMessage.id)
        .where(RetainedMailMessage.account_id == policy.account_id)
        .order_by(RetainedMailMessage.received_at.desc(), RetainedMailMessage.id.desc())
        .offset(policy.max_messages)
    )
    overflow_result = await session.execute(
        delete(RetainedMailMessage).where(RetainedMailMessage.id.in_(retained_ids))
    )
    await session.commit()
    old_count = int(cast(CursorResult[Any], old_result).rowcount or 0)
    overflow_count = int(cast(CursorResult[Any], overflow_result).rowcount or 0)
    return old_count + overflow_count


async def sync_retention_account(session: AsyncSession, account_id: uuid.UUID) -> dict[str, int]:
    policy = await session.get(RetentionPolicy, account_id)
    if not policy or not policy.enabled:
        raise ApiProblem(
            status=409,
            code="RETENTION_NOT_ENABLED",
            title="Mail retention is not enabled",
            detail="Enable a retention policy before syncing this account.",
        )
    folder_names = list(policy.folders)
    retain_bodies = policy.retain_bodies
    fetch_limit = min(policy.max_messages, 100)
    await session.commit()
    list_count = 0
    body_count = 0
    for folder in folder_names:
        page = await list_mail(
            session,
            account_id,
            folder=folder,
            offset=0,
            limit=fetch_limit,
            method="auto",
        )
        list_count += await cache_mail_page(session, account_id=account_id, page=page)
        if retain_bodies:
            for item in page.items[:20]:
                detail = await get_mail_detail(
                    session,
                    account_id,
                    folder=item.folder,
                    message_id=item.id,
                    method="auto",
                )
                await cache_mail_detail(session, account_id=account_id, detail=detail)
                body_count += 1
    policy = await session.get(RetentionPolicy, account_id, with_for_update=True)
    if policy:
        policy.last_synced_at = datetime.now(UTC)
        await prune_retained_mail(session, policy)
    return {"list_count": list_count, "body_count": body_count}


async def clear_retained_mail(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | None,
) -> int:
    statement = delete(RetainedMailMessage)
    if account_id:
        statement = statement.where(RetainedMailMessage.account_id == account_id)
    result = await session.execute(statement)
    await session.commit()
    return int(cast(CursorResult[Any], result).rowcount or 0)


async def get_retention_stats(session: AsyncSession) -> RetentionStatsRead:
    row = (
        await session.execute(
            select(
                func.count(func.distinct(RetainedMailMessage.account_id)),
                func.count(),
                func.count().filter(RetainedMailMessage.body.is_not(None)),
                func.coalesce(
                    func.sum(
                        func.octet_length(func.coalesce(RetainedMailMessage.body, ""))
                        + func.octet_length(func.coalesce(RetainedMailMessage.subject, ""))
                        + func.octet_length(func.coalesce(RetainedMailMessage.body_preview, ""))
                    ),
                    0,
                ),
            ).select_from(RetainedMailMessage)
        )
    ).one()
    accounts, messages, bodies, estimated = (int(value or 0) for value in row)
    return RetentionStatsRead(
        account_count=accounts,
        message_count=messages,
        body_count=bodies,
        estimated_bytes=estimated,
    )
