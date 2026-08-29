from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, delete, desc, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.accounts import (
    AccountArchiveRequest,
    AccountBulkChanges,
    AccountBulkMutation,
    AccountBulkResult,
    AccountCreate,
    AccountUpdate,
)
from smart_email_manager.api.schemas.views import AccountViewFilters
from smart_email_manager.db.models import (
    Account,
    AccountForwarding,
    AccountTag,
    Group,
    Tag,
)
from smart_email_manager.services.audit import add_audit_log
from smart_email_manager.services.organization import get_default_group_id


@dataclass(frozen=True)
class AccountCursor:
    created_at: datetime
    account_id: uuid.UUID


def encode_account_cursor(cursor: AccountCursor) -> str:
    payload = json.dumps(
        {"created_at": cursor.created_at.isoformat(), "id": str(cursor.account_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_account_cursor(value: str) -> AccountCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return AccountCursor(
            created_at=datetime.fromisoformat(payload["created_at"]),
            account_id=uuid.UUID(payload["id"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ApiProblem(
            status=400,
            code="INVALID_CURSOR",
            title="Invalid pagination cursor",
            detail="The supplied account cursor is malformed or expired.",
        ) from exc


def _apply_cursor(statement: Select[tuple[Account]], cursor: AccountCursor) -> Select[tuple[Account]]:
    return statement.where(
        or_(
            Account.created_at < cursor.created_at,
            and_(Account.created_at == cursor.created_at, Account.id < cursor.account_id),
        )
    )


async def list_accounts(
    session: AsyncSession,
    *,
    limit: int,
    cursor: str | None = None,
    lifecycle_status: str | None = None,
    token_status: str | None = None,
    mail_health_status: str | None = None,
    query: str | None = None,
    view_filters: AccountViewFilters | None = None,
) -> tuple[list[Account], str | None]:
    statement = select(Account)
    if view_filters:
        if view_filters.lifecycle_statuses:
            statement = statement.where(Account.lifecycle_status.in_(view_filters.lifecycle_statuses))
        if view_filters.authorization_statuses:
            statement = statement.where(Account.authorization_status.in_(view_filters.authorization_statuses))
        if view_filters.token_statuses:
            statement = statement.where(Account.token_status.in_(view_filters.token_statuses))
        if view_filters.mail_health_statuses:
            statement = statement.where(Account.mail_health_status.in_(view_filters.mail_health_statuses))
        if view_filters.proxy_health_statuses:
            statement = statement.where(Account.proxy_health_status.in_(view_filters.proxy_health_statuses))
        if view_filters.group_id:
            statement = statement.where(Account.group_id == view_filters.group_id)
        if view_filters.ungrouped:
            statement = statement.where(Account.group_id.is_(None))
        if view_filters.untagged:
            statement = statement.where(
                ~select(AccountTag.account_id).where(AccountTag.account_id == Account.id).exists()
            )
        if view_filters.min_consecutive_failures is not None:
            statement = statement.where(Account.consecutive_failures >= view_filters.min_consecutive_failures)
        if view_filters.last_mail_success_before is not None:
            statement = statement.where(
                or_(
                    Account.last_mail_success_at.is_(None),
                    Account.last_mail_success_at < view_filters.last_mail_success_before,
                )
            )
        if view_filters.query:
            normalized_view_query = view_filters.query.strip().lower()
            statement = statement.where(
                or_(
                    Account.email_normalized.contains(normalized_view_query),
                    Account.remark.ilike(f"%{normalized_view_query}%"),
                )
            )
    if lifecycle_status:
        statement = statement.where(Account.lifecycle_status == lifecycle_status)
    if token_status:
        statement = statement.where(Account.token_status == token_status)
    if mail_health_status:
        statement = statement.where(Account.mail_health_status == mail_health_status)
    if query:
        normalized = query.strip().lower()
        statement = statement.where(
            or_(
                Account.email_normalized.contains(normalized),
                Account.remark.ilike(f"%{normalized}%"),
            )
        )
    if cursor:
        statement = _apply_cursor(statement, decode_account_cursor(cursor))

    statement = statement.order_by(desc(Account.created_at), desc(Account.id)).limit(limit + 1)
    rows = list((await session.scalars(statement)).all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_account_cursor(AccountCursor(last.created_at, last.id))
    return items, next_cursor


async def create_account(session: AsyncSession, payload: AccountCreate) -> Account:
    normalized_email = str(payload.email).strip().lower()
    account = Account(
        email=str(payload.email).strip(),
        email_normalized=normalized_email,
        account_type=payload.account_type.strip().lower(),
        provider=payload.provider.strip().lower(),
        group_id=payload.group_id or await get_default_group_id(session),
        remark=payload.remark.strip(),
    )
    session.add(account)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="ACCOUNT_EMAIL_CONFLICT",
            title="Account already exists",
            detail=f"An account already uses {normalized_email}.",
        ) from exc
    await session.refresh(account)
    return account


async def get_account_or_404(session: AsyncSession, account_id: uuid.UUID) -> Account:
    account = await session.get(Account, account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    return account


async def update_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    payload: AccountUpdate,
) -> Account:
    account = await session.get(Account, account_id, with_for_update=True)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    if account.row_version != payload.row_version:
        raise ApiProblem(
            status=409,
            code="ACCOUNT_VERSION_CONFLICT",
            title="Account was updated concurrently",
            detail="Reload the account and retry with its current row_version.",
            context={"current_row_version": account.row_version},
        )
    if (
        "group_id" in payload.model_fields_set
        and payload.group_id
        and not await session.get(Group, payload.group_id)
    ):
        raise ApiProblem(
            status=404,
            code="GROUP_NOT_FOUND",
            title="Group not found",
            detail=f"No group exists with id {payload.group_id}.",
        )
    if payload.email is not None:
        account.email = str(payload.email).strip()
        account.email_normalized = account.email.lower()
    for field_name in (
        "account_type",
        "provider",
        "authorization_type",
        "lifecycle_status",
        "remark",
        "provider_metadata",
    ):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(account, field_name, value)
    if "group_id" in payload.model_fields_set:
        account.group_id = payload.group_id
    account.row_version += 1
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="ACCOUNT_EMAIL_CONFLICT",
            title="Account email already exists",
            detail="Another account already uses this email address.",
        ) from exc
    await session.refresh(account)
    return account


async def archive_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    payload: AccountArchiveRequest,
) -> Account:
    account = await session.get(Account, account_id, with_for_update=True)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    if account.row_version != payload.row_version:
        raise ApiProblem(
            status=409,
            code="ACCOUNT_VERSION_CONFLICT",
            title="Account was updated concurrently",
            detail="Reload the account and retry with its current row_version.",
        )
    account.lifecycle_status = "archived"
    account.row_version += 1
    add_audit_log(
        session,
        action="account.archive",
        resource_type="account",
        resource_id=str(account.id),
        data={"email": account.email},
    )
    await session.commit()
    await session.refresh(account)
    return account


async def purge_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    confirm_email: str,
) -> None:
    account = await get_account_or_404(session, account_id)
    if account.email_normalized != confirm_email.strip().lower():
        raise ApiProblem(
            status=409,
            code="ACCOUNT_PURGE_CONFIRMATION_MISMATCH",
            title="Account purge confirmation does not match",
            detail="confirm_email must exactly match the account email.",
        )
    add_audit_log(
        session,
        action="account.purge",
        resource_type="account",
        resource_id=str(account.id),
        data={"email": account.email},
    )
    await session.delete(account)
    await session.commit()


async def bulk_mutate_accounts(
    session: AsyncSession,
    payload: AccountBulkMutation,
    *,
    commit: bool = True,
) -> AccountBulkResult:
    requested_ids = list(dict.fromkeys(payload.account_ids))
    accounts = list(
        (await session.scalars(select(Account).where(Account.id.in_(requested_ids)).with_for_update())).all()
    )
    matched_ids = {account.id for account in accounts}
    await validate_bulk_changes(session, payload)
    updated_ids = await bulk_changed_account_ids(session, accounts, payload)
    for account in accounts:
        if account.id not in updated_ids:
            continue
        if payload.lifecycle_status is not None:
            account.lifecycle_status = payload.lifecycle_status
        if payload.move_group:
            account.group_id = payload.group_id
        account.row_version += 1
    if payload.remove_tag_ids:
        await session.execute(
            delete(AccountTag).where(
                AccountTag.account_id.in_(matched_ids),
                AccountTag.tag_id.in_(payload.remove_tag_ids),
            )
        )
    for account_id_value in matched_ids:
        for tag_id in payload.add_tag_ids:
            await session.execute(
                insert(AccountTag).values(account_id=account_id_value, tag_id=tag_id).on_conflict_do_nothing()
            )
    if payload.forwarding_enabled is not None:
        forwarding_rows = {
            row.account_id: row
            for row in (
                await session.scalars(
                    select(AccountForwarding).where(AccountForwarding.account_id.in_(matched_ids))
                )
            ).all()
        }
        for account_id_value in matched_ids:
            forwarding = forwarding_rows.get(account_id_value)
            if forwarding is None and payload.forwarding_enabled:
                forwarding = AccountForwarding(account_id=account_id_value)
                session.add(forwarding)
            if forwarding is not None:
                forwarding.enabled = payload.forwarding_enabled
    add_audit_log(
        session,
        action="account.bulk_mutate",
        resource_type="account_set",
        resource_id=None,
        data={
            "requested_count": len(requested_ids),
            "matched_count": len(accounts),
            "updated_count": len(updated_ids),
        },
    )
    if commit:
        await session.commit()
    else:
        await session.flush()
    return AccountBulkResult(
        requested_count=len(requested_ids),
        matched_count=len(accounts),
        updated_count=len(updated_ids),
        not_found_ids=[item for item in requested_ids if item not in matched_ids],
    )


async def validate_bulk_changes(
    session: AsyncSession,
    payload: AccountBulkChanges,
) -> None:
    if payload.move_group and payload.group_id and not await session.get(Group, payload.group_id):
        raise ApiProblem(
            status=404,
            code="GROUP_NOT_FOUND",
            title="Group not found",
            detail=f"No group exists with id {payload.group_id}.",
        )
    tag_ids = set(payload.add_tag_ids) | set(payload.remove_tag_ids)
    if tag_ids:
        existing_tag_ids = set((await session.scalars(select(Tag.id).where(Tag.id.in_(tag_ids)))).all())
        if existing_tag_ids != tag_ids:
            raise ApiProblem(
                status=404,
                code="TAG_NOT_FOUND",
                title="Tag not found",
                detail="At least one requested tag does not exist.",
            )


async def bulk_changed_account_ids(
    session: AsyncSession,
    accounts: list[Account],
    payload: AccountBulkChanges,
) -> set[uuid.UUID]:
    account_ids = {account.id for account in accounts}
    changed = {
        account.id
        for account in accounts
        if (payload.lifecycle_status is not None and account.lifecycle_status != payload.lifecycle_status)
        or (payload.move_group and account.group_id != payload.group_id)
    }
    requested_tag_ids = set(payload.add_tag_ids) | set(payload.remove_tag_ids)
    existing_tag_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    if account_ids and requested_tag_ids:
        tag_rows = (
            await session.execute(
                select(AccountTag.account_id, AccountTag.tag_id).where(
                    AccountTag.account_id.in_(account_ids),
                    AccountTag.tag_id.in_(requested_tag_ids),
                )
            )
        ).all()
        existing_tag_pairs = set(
            (account_id_value, tag_id) for account_id_value, tag_id in tag_rows
        )
    for account_id_value in account_ids:
        if any((account_id_value, tag_id) not in existing_tag_pairs for tag_id in payload.add_tag_ids) or any(
            (account_id_value, tag_id) in existing_tag_pairs for tag_id in payload.remove_tag_ids
        ):
            changed.add(account_id_value)
    if payload.forwarding_enabled is not None and account_ids:
        forwarding_rows = {
            row.account_id: row
            for row in (
                await session.scalars(
                    select(AccountForwarding).where(AccountForwarding.account_id.in_(account_ids))
                )
            ).all()
        }
        for account_id_value in account_ids:
            current = forwarding_rows.get(account_id_value)
            if bool(current and current.enabled) != payload.forwarding_enabled:
                changed.add(account_id_value)
    return changed
