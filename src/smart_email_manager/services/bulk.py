from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.accounts import (
    AccountBulkExecute,
    AccountBulkMutation,
    AccountBulkPreviewCreate,
    AccountBulkPreviewRead,
    AccountBulkResult,
)
from smart_email_manager.db.models import Account, AccountBulkPreview
from smart_email_manager.services.accounts import (
    bulk_changed_account_ids,
    bulk_mutate_accounts,
    list_accounts,
    validate_bulk_changes,
)
from smart_email_manager.services.views import resolve_account_view_filters

PREVIEW_TTL = timedelta(minutes=15)
MAX_FILTER_SELECTION = 20_000


def _token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


async def create_bulk_preview(
    session: AsyncSession,
    payload: AccountBulkPreviewCreate,
) -> AccountBulkPreviewRead:
    await validate_bulk_changes(session, payload.changes)
    selection = payload.selection
    if selection.scope == "ids":
        requested_ids = list(dict.fromkeys(selection.account_ids))
        accounts = list((await session.scalars(select(Account).where(Account.id.in_(requested_ids)))).all())
    else:
        view_filters = await resolve_account_view_filters(
            session,
            builtin_key=selection.view,
            saved_view_id=selection.saved_view_id,
        )
        accounts, next_cursor = await list_accounts(
            session,
            limit=MAX_FILTER_SELECTION,
            lifecycle_status=selection.lifecycle_status,
            token_status=selection.token_status,
            mail_health_status=selection.mail_health_status,
            query=selection.query,
            view_filters=view_filters,
        )
        if next_cursor:
            raise ApiProblem(
                status=422,
                code="BULK_SELECTION_TOO_LARGE",
                title="Bulk selection is too large",
                detail=f"A stable bulk preview can contain at most {MAX_FILTER_SELECTION} accounts.",
            )
    if not accounts:
        raise ApiProblem(
            status=409,
            code="BULK_SELECTION_EMPTY",
            title="Bulk selection is empty",
            detail="No existing accounts matched the requested bulk scope.",
        )
    changed_ids = await bulk_changed_account_ids(session, accounts, payload.changes)
    token = f"sem_bulk_{secrets.token_urlsafe(32)}"
    expires_at = datetime.now(UTC) + PREVIEW_TTL
    preview = AccountBulkPreview(
        token_hash=_token_hash(token),
        selection=selection.model_dump(mode="json", exclude_none=True),
        mutation=payload.changes.model_dump(mode="json", exclude_none=True),
        account_ids=[str(account.id) for account in accounts],
        matched_count=len(accounts),
        eligible_count=len(changed_ids),
        skipped_count=len(accounts) - len(changed_ids),
        dangerous_count=len(changed_ids) if payload.changes.lifecycle_status == "archived" else 0,
        expires_at=expires_at,
    )
    session.add(preview)
    await session.commit()
    return AccountBulkPreviewRead(
        preview_token=token,
        scope=selection.scope,
        matched_count=preview.matched_count,
        eligible_count=preview.eligible_count,
        skipped_count=preview.skipped_count,
        dangerous_count=preview.dangerous_count,
        expires_at=preview.expires_at,
    )


async def execute_bulk_preview(
    session: AsyncSession,
    payload: AccountBulkExecute,
) -> AccountBulkResult:
    token = payload.preview_token.get_secret_value()
    preview = await session.scalar(
        select(AccountBulkPreview)
        .where(AccountBulkPreview.token_hash == _token_hash(token))
        .with_for_update()
    )
    if not preview:
        raise ApiProblem(
            status=404,
            code="BULK_PREVIEW_NOT_FOUND",
            title="Bulk preview not found",
            detail="The bulk preview token is invalid.",
        )
    now = datetime.now(UTC)
    if preview.consumed_at:
        raise ApiProblem(
            status=409,
            code="BULK_PREVIEW_ALREADY_USED",
            title="Bulk preview was already used",
            detail="Bulk preview tokens are single-use.",
        )
    if preview.expires_at <= now:
        raise ApiProblem(
            status=410,
            code="BULK_PREVIEW_EXPIRED",
            title="Bulk preview expired",
            detail="Create a new preview to refresh the stable account selection.",
        )
    mutation = AccountBulkMutation.model_validate(
        {
            **preview.mutation,
            "account_ids": [uuid.UUID(value) for value in preview.account_ids],
        }
    )
    result = await bulk_mutate_accounts(session, mutation, commit=False)
    preview.consumed_at = now
    await session.commit()
    return result
