from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.imports import ImportBatchCreate
from smart_email_manager.db.models import (
    Account,
    AccountAlias,
    AccountSecret,
    Group,
    ImportBatch,
    ImportBatchItem,
)
from smart_email_manager.security.encryption import AccountSecretCipher

SEPARATOR = "----"


@dataclass
class ParsedImportLine:
    line_number: int
    status: str
    email: str | None = None
    email_normalized: str | None = None
    provider_metadata: dict[str, object] = field(default_factory=dict)
    password: str | None = None
    refresh_token: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _normalize_email(value: str) -> tuple[str, str]:
    validated = validate_email(value.strip(), check_deliverability=False)
    return value.strip(), validated.normalized.lower()


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value.strip())
        return True
    except (ValueError, AttributeError):
        return False


def parse_import_line(line: str, line_number: int, account_type: str) -> ParsedImportLine:
    parts = [part.strip() for part in line.split(SEPARATOR)]
    try:
        if account_type != "outlook":
            raise ValueError("Only Outlook imports are supported")
        if len(parts) != 4:
            raise ValueError("Outlook lines require email, password, client_id and refresh_token")
        email, normalized = _normalize_email(parts[0])
        password, third, fourth = parts[1:]
        if _is_uuid(third):
            client_id, refresh_token = third, fourth
        elif _is_uuid(fourth):
            refresh_token, client_id = third, fourth
        else:
            raise ValueError("Neither token field contains a valid client_id UUID")
        if not refresh_token:
            raise ValueError("refresh_token is empty")
        return ParsedImportLine(
            line_number=line_number,
            status="valid",
            email=email,
            email_normalized=normalized,
            provider_metadata={"client_id": client_id},
            password=password or None,
            refresh_token=refresh_token,
        )
    except (EmailNotValidError, ValueError) as exc:
        return ParsedImportLine(
            line_number=line_number,
            status="invalid",
            email=parts[0] if parts else None,
            error_code="IMPORT_LINE_INVALID",
            error_message=str(exc),
        )


def parse_import_content(content: str, account_type: str) -> list[ParsedImportLine]:
    lines = [(index, line.strip()) for index, line in enumerate(content.splitlines(), 1) if line.strip()]
    parsed = [parse_import_line(line, index, account_type) for index, line in lines]
    seen: set[str] = set()
    for item in parsed:
        if item.status != "valid" or not item.email_normalized:
            continue
        if item.email_normalized in seen:
            item.status = "conflict"
            item.error_code = "IMPORT_BATCH_DUPLICATE"
            item.error_message = "The same email appears more than once in this batch."
        seen.add(item.email_normalized)
    return parsed


def _batch_item_context(batch_id: uuid.UUID, line_number: int) -> str:
    return f"import:{batch_id}:line:{line_number}"


async def _existing_email_set(session: AsyncSession, emails: list[str]) -> set[str]:
    if not emails:
        return set()
    account_emails = await session.scalars(
        select(Account.email_normalized).where(Account.email_normalized.in_(emails))
    )
    alias_emails = await session.scalars(
        select(AccountAlias.email_normalized).where(AccountAlias.email_normalized.in_(emails))
    )
    return set(account_emails).union(alias_emails)


async def create_import_batch(
    session: AsyncSession,
    *,
    payload: ImportBatchCreate,
    cipher: AccountSecretCipher,
    idempotency_key: str | None,
) -> ImportBatch:
    if idempotency_key:
        existing = await session.scalar(
            select(ImportBatch)
            .options(selectinload(ImportBatch.items))
            .where(ImportBatch.idempotency_key == idempotency_key)
        )
        if existing:
            return existing
    if payload.group_id and not await session.get(Group, payload.group_id):
        raise ApiProblem(
            status=404,
            code="GROUP_NOT_FOUND",
            title="Group not found",
            detail=f"No group exists with id {payload.group_id}.",
        )

    parsed = parse_import_content(payload.content.get_secret_value(), payload.account_type)
    valid_emails = [
        item.email_normalized for item in parsed if item.email_normalized and item.status == "valid"
    ]
    existing_emails = await _existing_email_set(session, valid_emails)
    for item in parsed:
        if item.status == "valid" and item.email_normalized in existing_emails:
            item.status = "conflict"
            item.error_code = "ACCOUNT_EMAIL_CONFLICT"
            item.error_message = "The email already exists as a primary account or alias."

    batch = ImportBatch(
        status="validated",
        account_type=payload.account_type,
        provider=payload.provider.strip().lower(),
        group_id=payload.group_id,
        remark=payload.remark.strip(),
        idempotency_key=idempotency_key,
        total_count=len(parsed),
        valid_count=sum(item.status == "valid" for item in parsed),
        invalid_count=sum(item.status == "invalid" for item in parsed),
        conflict_count=sum(item.status == "conflict" for item in parsed),
    )
    session.add(batch)
    await session.flush()

    for parsed_item in parsed:
        context = _batch_item_context(batch.id, parsed_item.line_number)
        encrypted: dict[str, bytes | None] = {}
        for field_name in ("password", "refresh_token"):
            plaintext = getattr(parsed_item, field_name)
            encrypted[field_name] = (
                cipher.encrypt_context(context, field_name, plaintext).ciphertext if plaintext else None
            )
        session.add(
            ImportBatchItem(
                batch_id=batch.id,
                line_number=parsed_item.line_number,
                status=parsed_item.status,
                email=parsed_item.email,
                email_normalized=parsed_item.email_normalized,
                account_type=payload.account_type,
                provider=batch.provider,
                group_id=payload.group_id,
                remark=batch.remark,
                provider_metadata=parsed_item.provider_metadata,
                password_ciphertext=encrypted["password"],
                refresh_token_ciphertext=encrypted["refresh_token"],
                key_version=cipher.key_version if any(encrypted.values()) else None,
                error_code=parsed_item.error_code,
                error_message=parsed_item.error_message,
            )
        )
    await session.commit()
    return await get_import_batch(session, batch.id)


async def get_import_batch(session: AsyncSession, batch_id: uuid.UUID, *, lock: bool = False) -> ImportBatch:
    statement = select(ImportBatch).options(selectinload(ImportBatch.items)).where(ImportBatch.id == batch_id)
    if lock:
        statement = statement.with_for_update()
    batch = await session.scalar(statement)
    if not batch:
        raise ApiProblem(
            status=404,
            code="IMPORT_BATCH_NOT_FOUND",
            title="Import batch not found",
            detail=f"No import batch exists with id {batch_id}.",
        )
    return batch


async def list_import_batches(session: AsyncSession, limit: int) -> list[ImportBatch]:
    return list(
        (
            await session.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(limit))
        ).all()
    )


def _decrypt_staged_secret(
    cipher: AccountSecretCipher,
    item: ImportBatchItem,
    field_name: str,
) -> str | None:
    ciphertext = getattr(item, f"{field_name}_ciphertext")
    if not ciphertext or item.key_version is None:
        return None
    return cipher.decrypt_context(
        _batch_item_context(item.batch_id, item.line_number),
        field_name,
        ciphertext,
        item.key_version,
    )


async def commit_import_batch(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID,
    cipher: AccountSecretCipher,
) -> ImportBatch:
    batch = await get_import_batch(session, batch_id, lock=True)
    if batch.status in {"completed", "partial"}:
        return batch
    if batch.status != "validated":
        raise ApiProblem(
            status=409,
            code="IMPORT_BATCH_NOT_COMMITTABLE",
            title="Import batch cannot be committed",
            detail=f"Batch status is {batch.status}.",
        )
    batch.status = "committing"
    await session.flush()

    for item in batch.items:
        if item.status != "valid" or not item.email or not item.email_normalized:
            continue
        existing = await session.scalar(
            select(Account.id).where(Account.email_normalized == item.email_normalized)
        )
        alias = await session.scalar(
            select(AccountAlias.id).where(AccountAlias.email_normalized == item.email_normalized)
        )
        if existing or alias:
            item.status = "skipped"
            item.error_code = "ACCOUNT_EMAIL_CONFLICT"
            item.error_message = "The email became occupied after preflight."
            continue
        try:
            async with session.begin_nested():
                account = Account(
                    email=item.email,
                    email_normalized=item.email_normalized,
                    account_type=item.account_type,
                    provider=item.provider,
                    group_id=item.group_id,
                    remark=item.remark,
                    provider_metadata=item.provider_metadata,
                )
                session.add(account)
                await session.flush()
                secrets_by_field = {
                    field_name: _decrypt_staged_secret(cipher, item, field_name)
                    for field_name in ("password", "refresh_token")
                }
                secret_row = AccountSecret(account_id=account.id, key_version=cipher.key_version)
                has_secret = False
                for field_name, plaintext in secrets_by_field.items():
                    if plaintext is None:
                        continue
                    encrypted = cipher.encrypt(account.id, field_name, plaintext)
                    setattr(secret_row, f"{field_name}_ciphertext", encrypted.ciphertext)
                    has_secret = True
                if has_secret:
                    session.add(secret_row)
                item.created_account_id = account.id
                item.status = "created"
                item.password_ciphertext = None
                item.refresh_token_ciphertext = None
        except (IntegrityError, ValueError) as exc:
            item.status = "failed"
            item.error_code = "IMPORT_COMMIT_FAILED"
            item.error_message = str(exc)[:500]

    batch.created_count = sum(item.status == "created" for item in batch.items)
    batch.skipped_count = sum(item.status == "skipped" for item in batch.items)
    batch.failed_count = sum(item.status == "failed" for item in batch.items)
    batch.finished_at = datetime.now(UTC)
    non_created = batch.invalid_count + batch.conflict_count + batch.skipped_count + batch.failed_count
    if batch.created_count and non_created:
        batch.status = "partial"
    elif batch.failed_count:
        batch.status = "failed"
    else:
        batch.status = "completed"
    await session.commit()
    return await get_import_batch(session, batch.id)


async def rollback_import_batch(session: AsyncSession, batch_id: uuid.UUID) -> ImportBatch:
    batch = await get_import_batch(session, batch_id, lock=True)
    if batch.status not in {"completed", "partial"}:
        raise ApiProblem(
            status=409,
            code="IMPORT_BATCH_NOT_ROLLBACKABLE",
            title="Import batch cannot be rolled back",
            detail=f"Batch status is {batch.status}.",
        )
    guarded = 0
    for item in batch.items:
        if item.status != "created" or not item.created_account_id:
            continue
        account = await session.get(Account, item.created_account_id, with_for_update=True)
        if account and account.row_version == 1:
            await session.execute(delete(Account).where(Account.id == account.id))
            item.status = "rolled_back"
            item.created_account_id = None
        else:
            guarded += 1
            item.error_code = "ROLLBACK_GUARD_BLOCKED"
            item.error_message = "Account changed after import and was not deleted."
    batch.status = "partial" if guarded else "rolled_back"
    batch.finished_at = datetime.now(UTC)
    await session.commit()
    return await get_import_batch(session, batch.id)
