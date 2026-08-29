from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.forwarding import (
    AccountForwardingRead,
    AccountForwardingWrite,
    ForwardingDeliveryRead,
    ForwardingDestinationRead,
    ForwardingDestinationWrite,
    ForwardingTestResult,
)
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import (
    Account,
    AccountForwarding,
    AccountForwardingDestination,
    ForwardingDelivery,
    ForwardingDestination,
)
from smart_email_manager.providers.forwarding import ForwardingSender, ForwardPayload
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.mail import get_mail_detail, list_mail

FORWARDING_SENDER = ForwardingSender()


def _context(destination_id: uuid.UUID) -> str:
    return f"forwarding:{destination_id}"


def _validate_destination(payload: ForwardingDestinationWrite, *, secret_required: bool) -> None:
    config = payload.config
    if payload.channel == "smtp":
        required = ("host", "recipient")
        if not all(str(config.get(item) or "").strip() for item in required):
            raise ApiProblem(
                status=422,
                code="SMTP_CONFIG_INCOMPLETE",
                title="SMTP destination is incomplete",
                detail="SMTP forwarding requires host and recipient.",
            )
    if secret_required and (not payload.secret or not payload.secret.get_secret_value().strip()):
        raise ApiProblem(
            status=422,
            code="FORWARDING_SECRET_REQUIRED",
            title="Forwarding destination secret is required",
            detail="Provide the SMTP password.",
        )


def _serialize_destination(row: ForwardingDestination) -> ForwardingDestinationRead:
    return ForwardingDestinationRead(
        id=row.id,
        name=row.name,
        channel=row.channel,
        enabled=row.enabled,
        config=row.config,
        has_secret=bool(row.secret_ciphertext),
        key_version=row.key_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def write_forwarding_destination(
    session: AsyncSession,
    *,
    payload: ForwardingDestinationWrite,
    cipher: AccountSecretCipher,
    destination_id: uuid.UUID | None = None,
) -> ForwardingDestinationRead:
    row = await session.get(ForwardingDestination, destination_id) if destination_id else None
    if destination_id and not row:
        raise ApiProblem(
            status=404,
            code="FORWARDING_DESTINATION_NOT_FOUND",
            title="Forwarding destination not found",
            detail=f"No forwarding destination exists with id {destination_id}.",
        )
    _validate_destination(payload, secret_required=row is None)
    if row is None:
        row = ForwardingDestination(
            name=payload.name.strip(),
            channel=payload.channel,
            config=payload.config,
            secret_ciphertext=b"pending",
            key_version=cipher.key_version,
        )
        session.add(row)
        await session.flush()
    elif row.key_version != cipher.key_version:
        raise ApiProblem(
            status=409,
            code="FORWARDING_KEY_ROTATION_REQUIRED",
            title="Forwarding destination uses another key version",
            detail="Rotate this destination before updating it.",
        )
    row.name = payload.name.strip()
    row.channel = payload.channel
    row.enabled = payload.enabled
    row.config = payload.config
    if payload.secret is not None:
        row.secret_ciphertext = cipher.encrypt_context(
            _context(row.id),
            "secret",
            payload.secret.get_secret_value(),
        ).ciphertext
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="FORWARDING_DESTINATION_NAME_CONFLICT",
            title="Forwarding destination name already exists",
            detail=f"A destination already uses {payload.name.strip()}.",
        ) from exc
    await session.refresh(row)
    return _serialize_destination(row)


async def list_forwarding_destinations(
    session: AsyncSession,
) -> list[ForwardingDestinationRead]:
    rows = (await session.scalars(select(ForwardingDestination).order_by(ForwardingDestination.name))).all()
    return [_serialize_destination(row) for row in rows]


async def delete_forwarding_destination(
    session: AsyncSession,
    destination_id: uuid.UUID,
) -> None:
    row = await session.get(ForwardingDestination, destination_id)
    if not row:
        raise ApiProblem(
            status=404,
            code="FORWARDING_DESTINATION_NOT_FOUND",
            title="Forwarding destination not found",
            detail=f"No forwarding destination exists with id {destination_id}.",
        )
    await session.delete(row)
    await session.commit()


async def _decrypt_destination_secret(
    row: ForwardingDestination,
    cipher: AccountSecretCipher,
) -> str:
    return cipher.decrypt_context(
        _context(row.id),
        "secret",
        row.secret_ciphertext,
        row.key_version,
    )


async def test_forwarding_destination(
    session: AsyncSession,
    destination_id: uuid.UUID,
    cipher: AccountSecretCipher,
) -> ForwardingTestResult:
    row = await session.get(ForwardingDestination, destination_id)
    if not row:
        raise ApiProblem(
            status=404,
            code="FORWARDING_DESTINATION_NOT_FOUND",
            title="Forwarding destination not found",
            detail=f"No forwarding destination exists with id {destination_id}.",
        )
    secret = await _decrypt_destination_secret(row, cipher)
    channel = row.channel
    config = dict(row.config)
    await session.commit()
    result = await FORWARDING_SENDER.send(
        channel=channel,
        config=config,
        secret=secret,
        payload=ForwardPayload(
            subject="Smart Email Manager forwarding test",
            text="This is a forwarding destination test.",
        ),
    )
    return ForwardingTestResult(**result.__dict__)


async def write_account_forwarding(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    payload: AccountForwardingWrite,
) -> AccountForwardingRead:
    if not await session.get(Account, account_id):
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    destination_ids = list(dict.fromkeys(payload.destination_ids))
    if destination_ids:
        existing_ids = set(
            (
                await session.scalars(
                    select(ForwardingDestination.id).where(ForwardingDestination.id.in_(destination_ids))
                )
            ).all()
        )
        missing = [item for item in destination_ids if item not in existing_ids]
        if missing:
            raise ApiProblem(
                status=422,
                code="FORWARDING_DESTINATION_NOT_FOUND",
                title="Forwarding destination not found",
                detail=f"Unknown forwarding destination: {missing[0]}.",
            )
    row = await session.get(AccountForwarding, account_id)
    if row is None:
        row = AccountForwarding(account_id=account_id)
        session.add(row)
    row.enabled = payload.enabled
    row.include_junk = payload.include_junk
    row.window_minutes = payload.window_minutes
    await session.flush()
    await session.execute(
        delete(AccountForwardingDestination).where(AccountForwardingDestination.account_id == account_id)
    )
    for destination_id in destination_ids:
        session.add(
            AccountForwardingDestination(
                account_id=account_id,
                destination_id=destination_id,
            )
        )
    await session.commit()
    await session.refresh(row)
    return AccountForwardingRead(
        account_id=account_id,
        enabled=row.enabled,
        include_junk=row.include_junk,
        window_minutes=row.window_minutes,
        cursor_at=row.cursor_at,
        destination_ids=destination_ids,
        updated_at=row.updated_at,
    )


async def get_account_forwarding(
    session: AsyncSession,
    account_id: uuid.UUID,
) -> AccountForwardingRead:
    if not await session.get(Account, account_id):
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    row = await session.get(AccountForwarding, account_id)
    ids = list(
        (
            await session.scalars(
                select(AccountForwardingDestination.destination_id).where(
                    AccountForwardingDestination.account_id == account_id
                )
            )
        ).all()
    )
    return AccountForwardingRead(
        account_id=account_id,
        enabled=bool(row and row.enabled),
        include_junk=bool(row and row.include_junk),
        window_minutes=row.window_minutes if row else 0,
        cursor_at=row.cursor_at if row else None,
        destination_ids=ids,
        updated_at=row.updated_at if row else None,
    )


async def reset_forwarding_cursor(
    session: AsyncSession,
    account_id: uuid.UUID,
    cursor_at: datetime | None,
) -> AccountForwardingRead:
    row = await session.get(AccountForwarding, account_id, with_for_update=True)
    if not row:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_FORWARDING_NOT_FOUND",
            title="Account forwarding is not configured",
            detail="Configure forwarding before resetting its cursor.",
        )
    row.cursor_at = cursor_at
    await session.commit()
    return await get_account_forwarding(session, account_id)


async def list_forwarding_deliveries(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | None,
    limit: int,
) -> list[ForwardingDeliveryRead]:
    statement = select(ForwardingDelivery).order_by(ForwardingDelivery.created_at.desc()).limit(limit)
    if account_id:
        statement = statement.where(ForwardingDelivery.account_id == account_id)
    return [ForwardingDeliveryRead.model_validate(row) for row in (await session.scalars(statement)).all()]


def _parse_received_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _forward_payload(account: Account, detail: Any) -> ForwardPayload:
    subject = f"[{account.email}] {detail.subject or 'No subject'}"
    text = (
        f"Mailbox: {account.email}\nFrom: {detail.sender}\nTo: {', '.join(detail.recipients)}\n"
        f"Received: {detail.received_at}\n\n{detail.body}"
    )
    return ForwardPayload(
        subject=subject[:250],
        text=text,
        html=detail.body if detail.body_type == "html" else "",
    )


async def _claim_delivery(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    message_id: str,
    folder: str,
    destination: ForwardingDestination,
) -> ForwardingDelivery | None:
    row = await session.scalar(
        select(ForwardingDelivery)
        .where(
            ForwardingDelivery.account_id == account_id,
            ForwardingDelivery.message_id == message_id,
            ForwardingDelivery.destination_id == destination.id,
        )
        .with_for_update()
    )
    if row and row.status == "success":
        await session.rollback()
        return None
    if row and row.status == "processing" and row.updated_at > datetime.now(UTC) - timedelta(minutes=5):
        await session.rollback()
        return None
    if row is None:
        row = ForwardingDelivery(
            account_id=account_id,
            message_id=message_id,
            folder=folder,
            destination_id=destination.id,
            channel=destination.channel,
            status="processing",
            attempt_count=1,
        )
        session.add(row)
    else:
        row.status = "processing"
        row.attempt_count += 1
        row.error_code = None
        row.error_summary = None
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    await session.refresh(row)
    return row


async def run_forwarding_account(
    session: AsyncSession,
    account_id: uuid.UUID,
) -> dict[str, int]:
    account = await session.get(Account, account_id)
    config = await session.get(AccountForwarding, account_id)
    if not account or not config or not config.enabled:
        raise ApiProblem(
            status=409,
            code="FORWARDING_NOT_ENABLED",
            title="Forwarding is not enabled",
            detail="Enable account forwarding before running a scan.",
        )
    destinations = list(
        (
            await session.scalars(
                select(ForwardingDestination)
                .join(
                    AccountForwardingDestination,
                    AccountForwardingDestination.destination_id == ForwardingDestination.id,
                )
                .where(
                    AccountForwardingDestination.account_id == account_id,
                    ForwardingDestination.enabled.is_(True),
                )
            )
        ).all()
    )
    if not destinations:
        raise ApiProblem(
            status=409,
            code="FORWARDING_DESTINATION_MISSING",
            title="No forwarding destination is enabled",
            detail="Assign at least one enabled destination to this account.",
        )
    cursor_at = config.cursor_at
    window_start = (
        datetime.now(UTC) - timedelta(minutes=config.window_minutes) if config.window_minutes else None
    )
    folders = ["inbox", "junkemail"] if config.include_junk else ["inbox"]
    await session.commit()
    candidates: list[Any] = []
    for folder in folders:
        page = await list_mail(
            session,
            account_id,
            folder=folder,
            offset=0,
            limit=50,
            method="auto",
        )
        for item in page.items:
            received = _parse_received_at(item.received_at)
            if cursor_at and received and received <= cursor_at:
                continue
            if window_start and received and received < window_start:
                continue
            candidates.append(item)
    candidates.sort(key=lambda item: _parse_received_at(item.received_at) or datetime.min.replace(tzinfo=UTC))

    sent = 0
    skipped = 0
    failed = 0
    retryable_failed = 0
    latest = cursor_at
    cipher = AccountSecretCipher.from_settings(get_settings())
    for item in candidates:
        detail = await get_mail_detail(
            session,
            account_id,
            folder=item.folder,
            message_id=item.id,
            method="auto",
        )
        payload = _forward_payload(account, detail)
        message_failed = False
        for destination in destinations:
            delivery = await _claim_delivery(
                session,
                account_id=account_id,
                message_id=item.id,
                folder=item.folder,
                destination=destination,
            )
            if delivery is None:
                skipped += 1
                continue
            secret = await _decrypt_destination_secret(destination, cipher)
            await session.commit()
            result = await FORWARDING_SENDER.send(
                channel=destination.channel,
                config=dict(destination.config),
                secret=secret,
                payload=payload,
            )
            delivery = await session.get(ForwardingDelivery, delivery.id, with_for_update=True)
            if delivery:
                delivery.status = "success" if result.success else "failed"
                delivery.error_code = None if result.success else result.reason_code
                delivery.error_summary = None if result.success else result.message
                delivery.sent_at = datetime.now(UTC) if result.success else None
                await session.commit()
            if result.success:
                sent += 1
            else:
                failed += 1
                if result.retryable:
                    retryable_failed += 1
                message_failed = True
        received = _parse_received_at(item.received_at)
        if not message_failed and received and (latest is None or received > latest):
            latest = received
    if failed == 0 and latest and latest != cursor_at:
        config = await session.get(AccountForwarding, account_id, with_for_update=True)
        if config:
            config.cursor_at = latest
            await session.commit()
    return {
        "candidate_count": len(candidates),
        "sent_count": sent,
        "skipped_count": skipped,
        "failed_count": failed,
        "retryable_failed_count": retryable_failed,
    }
