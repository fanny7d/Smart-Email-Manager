from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import (
    Account,
    AccountHealthSnapshot,
    AccountSecret,
    TokenRefreshLog,
)
from smart_email_manager.domain.enums import (
    AuthorizationStatus,
    JobItemStatus,
    MailHealthStatus,
    TokenStatus,
)
from smart_email_manager.jobs.queue import LeasedJobItem, finish_item, retry_item
from smart_email_manager.providers.base import ProviderAccount
from smart_email_manager.providers.registry import ProviderRegistry
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.forwarding import run_forwarding_account
from smart_email_manager.services.proxies import resolve_account_proxy
from smart_email_manager.services.retention import sync_retention_account
from smart_email_manager.services.secrets import load_decrypted_account_secrets

PROVIDER_REGISTRY = ProviderRegistry()


async def handle_metadata_health_check(session: AsyncSession, lease: LeasedJobItem) -> None:
    if lease.subject_id is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.FAILED,
            error_code="SUBJECT_MISSING",
            error_summary="The job item has no account id.",
        )
        return

    account = await session.get(Account, lease.subject_id, with_for_update=True)
    if account is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.SKIPPED,
            result={"reason_code": "ACCOUNT_NOT_FOUND"},
        )
        return

    missing_fields = [
        name
        for name, value in {
            "email": account.email,
            "email_normalized": account.email_normalized,
            "provider": account.provider,
            "account_type": account.account_type,
        }.items()
        if not str(value or "").strip()
    ]
    now = datetime.now(UTC)
    if missing_fields:
        status = MailHealthStatus.DEGRADED
        reason_code = "ACCOUNT_METADATA_INCOMPLETE"
        account.health_error_summary = f"Missing required metadata: {', '.join(missing_fields)}"
        account.consecutive_failures += 1
    else:
        status = MailHealthStatus.UNKNOWN
        reason_code = "REMOTE_CHECK_NOT_RUN"
        account.health_error_summary = None

    account.mail_health_status = status
    account.health_reason_code = reason_code
    account.last_mail_check_at = now
    session.add(
        AccountHealthSnapshot(
            account_id=account.id,
            mode="metadata",
            status=status,
            reason_code=reason_code,
            details={"missing_fields": missing_fields},
            checked_at=now,
        )
    )
    await finish_item(
        session,
        lease,
        status=JobItemStatus.SUCCEEDED,
        result={
            "account_id": str(account.id),
            "mail_health_status": status,
            "reason_code": reason_code,
            "missing_fields": missing_fields,
        },
    )


async def handle_connectivity_health_check(session: AsyncSession, lease: LeasedJobItem) -> None:
    if lease.subject_id is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.FAILED,
            error_code="SUBJECT_MISSING",
            error_summary="The job item has no account id.",
        )
        return

    account = await session.get(Account, lease.subject_id)
    if account is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.SKIPPED,
            result={"reason_code": "ACCOUNT_NOT_FOUND"},
        )
        return
    cipher = AccountSecretCipher.from_settings(get_settings())
    secrets = await load_decrypted_account_secrets(
        session,
        account_id=account.id,
        cipher=cipher,
    )
    resolved_proxy = await resolve_account_proxy(session, account.id, cipher)
    provider_account = ProviderAccount(
        id=account.id,
        email=account.email,
        account_type=account.account_type,
        provider=account.provider,
        authorization_type=account.authorization_type,
        provider_metadata=dict(account.provider_metadata),
        proxy_urls=resolved_proxy.urls,
    )
    # End the read transaction before any network call.
    await session.commit()
    result = await PROVIDER_REGISTRY.check_health(provider_account, secrets)

    account = await session.get(Account, lease.subject_id, with_for_update=True)
    if account is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.SKIPPED,
            result={"reason_code": "ACCOUNT_REMOVED_DURING_CHECK"},
        )
        return
    now = datetime.now(UTC)
    account.last_mail_check_at = now
    account.mail_health_status = result.status
    account.health_reason_code = result.reason_code
    account.health_error_summary = result.message or None
    if result.success:
        account.last_mail_success_at = now
        account.consecutive_failures = 0
        account.authorization_status = AuthorizationStatus.VALID
        account.token_status = TokenStatus.SUCCESS
        account.last_token_check_at = now
        if result.channel in {"graph", "imap"}:
            account.authorization_type = result.channel
    else:
        account.consecutive_failures += 1
        attempt_reason_codes: list[str] = []
        attempts = result.details.get("attempts")
        if isinstance(attempts, list):
            attempt_reason_codes = [
                str(item.get("reason_code") or "")
                for item in attempts
                if isinstance(item, dict) and item.get("reason_code")
            ]
        classified_codes = attempt_reason_codes or [result.reason_code]
        if classified_codes and all(
            "CREDENTIAL" in code or "TOKEN" in code for code in classified_codes
        ):
            account.authorization_status = AuthorizationStatus.INVALID
            account.token_status = TokenStatus.FAILED
            account.last_token_check_at = now
    session.add(
        AccountHealthSnapshot(
            account_id=account.id,
            mode="connectivity",
            status=result.status,
            channel=result.channel,
            reason_code=result.reason_code,
            details={
                "message": result.message,
                "retryable": result.retryable,
                **result.details,
            },
            checked_at=now,
        )
    )
    await finish_item(
        session,
        lease,
        status=JobItemStatus.SUCCEEDED,
        result={
            "account_id": str(account.id),
            "mail_health_status": result.status,
            "channel": result.channel,
            "reason_code": result.reason_code,
            "retryable": result.retryable,
        },
    )


async def handle_health_check(session: AsyncSession, lease: LeasedJobItem) -> None:
    if lease.payload.get("mode") == "connectivity":
        await handle_connectivity_health_check(session, lease)
    else:
        await handle_metadata_health_check(session, lease)


async def handle_token_refresh(session: AsyncSession, lease: LeasedJobItem) -> None:
    if lease.subject_id is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.FAILED,
            error_code="SUBJECT_MISSING",
            error_summary="The job item has no account id.",
        )
        return

    account = await session.get(Account, lease.subject_id)
    if account is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.SKIPPED,
            result={"reason_code": "ACCOUNT_NOT_FOUND"},
        )
        return
    cipher = AccountSecretCipher.from_settings(get_settings())
    secrets = await load_decrypted_account_secrets(
        session,
        account_id=account.id,
        cipher=cipher,
    )
    resolved_proxy = await resolve_account_proxy(session, account.id, cipher)
    provider_account = ProviderAccount(
        id=account.id,
        email=account.email,
        account_type=account.account_type,
        provider=account.provider,
        authorization_type=account.authorization_type,
        provider_metadata=dict(account.provider_metadata),
        proxy_urls=resolved_proxy.urls,
    )
    # Never keep a database transaction open while waiting on a remote provider.
    await session.commit()
    result = await PROVIDER_REGISTRY.refresh_authorization(provider_account, secrets)

    account = await session.get(Account, lease.subject_id, with_for_update=True)
    secret_row = await session.get(AccountSecret, lease.subject_id, with_for_update=True)
    if account is None or secret_row is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.SKIPPED,
            result={"reason_code": "ACCOUNT_REMOVED_DURING_REFRESH"},
        )
        return

    now = datetime.now(UTC)
    account.last_token_check_at = now
    account.health_reason_code = result.reason_code
    account.health_error_summary = result.message or None
    rotated = bool(result.success and result.rotated_refresh_token)
    if result.success:
        if rotated:
            if secret_row.key_version != cipher.key_version:
                raise RuntimeError(f"Account secret key version {secret_row.key_version} is not active")
            encrypted = cipher.encrypt(
                account.id,
                "refresh_token",
                result.rotated_refresh_token or "",
            )
            secret_row.refresh_token_ciphertext = encrypted.ciphertext
        account.token_status = TokenStatus.SUCCESS
        account.authorization_status = AuthorizationStatus.VALID
        if result.channel in {"graph", "imap"}:
            account.authorization_type = result.channel
    else:
        account.token_status = TokenStatus.FAILED
        if not result.retryable:
            account.authorization_status = AuthorizationStatus.REAUTHORIZATION_REQUIRED

    session.add(
        TokenRefreshLog(
            account_id=account.id,
            job_id=lease.job_id,
            status="success" if result.success else "failed",
            channel=result.channel,
            reason_code=result.reason_code,
            error_summary=result.message or None,
            rotated=rotated,
        )
    )
    if result.success:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.SUCCEEDED,
            result={
                "account_id": str(account.id),
                "channel": result.channel,
                "reason_code": result.reason_code,
                "rotated": rotated,
                "details": result.details,
            },
        )
    else:
        failure_result = {
            "account_id": str(account.id),
            "channel": result.channel,
            "retryable": result.retryable,
            "details": result.details,
        }
        if result.retryable:
            await retry_item(
                session,
                lease,
                error_code=result.reason_code,
                error_summary=result.message or "Token refresh failed.",
                result=failure_result,
            )
        else:
            await finish_item(
                session,
                lease,
                status=JobItemStatus.FAILED,
                error_code=result.reason_code,
                error_summary=result.message or "Token refresh failed.",
                result=failure_result,
            )


async def handle_retention_sync(session: AsyncSession, lease: LeasedJobItem) -> None:
    if lease.subject_id is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.FAILED,
            error_code="SUBJECT_MISSING",
            error_summary="The job item has no account id.",
        )
        return
    try:
        result = await sync_retention_account(session, lease.subject_id)
    except ApiProblem as exc:
        if exc.problem.status >= 500:
            await retry_item(
                session,
                lease,
                error_code=exc.problem.code,
                error_summary=exc.problem.detail,
            )
        else:
            await finish_item(
                session,
                lease,
                status=JobItemStatus.FAILED,
                error_code=exc.problem.code,
                error_summary=exc.problem.detail,
            )
        return
    await finish_item(
        session,
        lease,
        status=JobItemStatus.SUCCEEDED,
        result={"account_id": str(lease.subject_id), **result},
    )


async def handle_forwarding_scan(session: AsyncSession, lease: LeasedJobItem) -> None:
    if lease.subject_id is None:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.FAILED,
            error_code="SUBJECT_MISSING",
            error_summary="The job item has no account id.",
        )
        return
    try:
        result = await run_forwarding_account(session, lease.subject_id)
    except ApiProblem as exc:
        if exc.problem.status >= 500:
            await retry_item(
                session,
                lease,
                error_code=exc.problem.code,
                error_summary=exc.problem.detail,
            )
        else:
            await finish_item(
                session,
                lease,
                status=JobItemStatus.FAILED,
                error_code=exc.problem.code,
                error_summary=exc.problem.detail,
            )
        return
    item_result = {"account_id": str(lease.subject_id), **result}
    if result["failed_count"]:
        error_summary = f"{result['failed_count']} forwarding delivery attempt(s) failed."
        if result["retryable_failed_count"]:
            await retry_item(
                session,
                lease,
                error_code="FORWARDING_DELIVERY_FAILED",
                error_summary=error_summary,
                result=item_result,
            )
        else:
            await finish_item(
                session,
                lease,
                status=JobItemStatus.FAILED,
                error_code="FORWARDING_DELIVERY_FAILED",
                error_summary=error_summary,
                result=item_result,
            )
    else:
        await finish_item(
            session,
            lease,
            status=JobItemStatus.SUCCEEDED,
            result=item_result,
        )


HANDLERS = {
    "account.health_check": handle_health_check,
    "account.metadata_health_check": handle_health_check,
    "account.token_refresh": handle_token_refresh,
    "account.retention_sync": handle_retention_sync,
    "account.forwarding_scan": handle_forwarding_scan,
}
