from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, NoReturn, cast

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.mail import MailDetailRead, MailPageRead, MailSummaryRead
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import Account, RetainedMailMessage
from smart_email_manager.providers.base import (
    DownloadedAttachment,
    MailMessageDetail,
    MailPage,
    MailProvider,
    ProviderAccount,
    ProviderOperationError,
)
from smart_email_manager.providers.registry import ProviderRegistry, proxy_variants
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.audit import add_audit_log
from smart_email_manager.services.proxies import resolve_account_proxy
from smart_email_manager.services.secrets import (
    DecryptedAccountSecrets,
    load_decrypted_account_secrets,
)

MAIL_REGISTRY = ProviderRegistry()


async def _provider_context(
    session: AsyncSession,
    account_id: uuid.UUID,
) -> tuple[ProviderAccount, DecryptedAccountSecrets]:
    account = await session.get(Account, account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    secrets = await load_decrypted_account_secrets(
        session,
        account_id=account.id,
        cipher=AccountSecretCipher.from_settings(get_settings()),
    )
    resolved_proxy = await resolve_account_proxy(
        session,
        account.id,
        AccountSecretCipher.from_settings(get_settings()),
    )
    provider_account = ProviderAccount(
        id=account.id,
        email=account.email,
        account_type=account.account_type,
        provider=account.provider,
        authorization_type=account.authorization_type,
        provider_metadata=dict(account.provider_metadata),
        proxy_urls=resolved_proxy.urls,
    )
    await session.commit()
    return provider_account, secrets


def _providers(
    account: ProviderAccount,
    method: str | None,
) -> list[MailProvider]:
    providers = MAIL_REGISTRY.ordered_providers(account, method)
    if not providers:
        raise ApiProblem(
            status=400,
            code="MAIL_METHOD_INVALID",
            title="Mail method is invalid for this account",
            detail=f"Requested method {method!r} is not supported.",
        )
    return providers


def _records_account_wide_failure(method: str | None) -> bool:
    """Only automatic provider selection represents the account's overall health."""
    return method in {None, "auto"}


async def _record_success(session: AsyncSession, account_id: uuid.UUID, method: str) -> None:
    account = await session.get(Account, account_id, with_for_update=True)
    if not account:
        return
    now = datetime.now(UTC)
    account.last_mail_check_at = now
    account.last_mail_success_at = now
    account.mail_health_status = "healthy"
    account.authorization_status = "valid"
    account.health_reason_code = f"{method.upper()}_OK"
    account.health_error_summary = None
    account.consecutive_failures = 0
    account.authorization_type = method
    account.token_status = "success"
    account.last_token_check_at = now
    await session.commit()


async def _record_failure(
    session: AsyncSession,
    account_id: uuid.UUID,
    attempts: list[ProviderOperationError],
) -> None:
    account = await session.get(Account, account_id, with_for_update=True)
    if not account:
        return
    account.last_mail_check_at = datetime.now(UTC)
    account.mail_health_status = "failed"
    account.health_reason_code = "ALL_PROVIDER_CHANNELS_FAILED"
    account.health_error_summary = " | ".join(item.code for item in attempts)[:500]
    account.consecutive_failures += 1
    await session.commit()


def _raise_attempts(attempts: list[ProviderOperationError]) -> NoReturn:
    if not attempts:
        raise ApiProblem(
            status=500,
            code="MAIL_PROVIDER_UNAVAILABLE",
            title="No mail provider is available",
            detail="No provider adapter could handle the account.",
        )
    raise ApiProblem(
        status=attempts[-1].status,
        code="ALL_PROVIDER_CHANNELS_FAILED",
        title="All mail provider channels failed",
        detail="Every configured provider channel failed.",
        context={
            "attempts": [
                {
                    "code": item.code,
                    "message": item.message,
                    "retryable": item.retryable,
                }
                for item in attempts
            ]
        },
    )


async def _list_single_folder(
    account: ProviderAccount,
    secrets: DecryptedAccountSecrets,
    *,
    folder: str,
    offset: int,
    limit: int,
    method: str | None,
) -> tuple[MailPage, list[ProviderOperationError]]:
    attempts: list[ProviderOperationError] = []
    for provider in _providers(account, method):
        for account_attempt in proxy_variants(account):
            try:
                return (
                    await provider.list_messages(
                        account_attempt,
                        secrets,
                        folder=folder,
                        offset=offset,
                        limit=limit,
                    ),
                    attempts,
                )
            except ProviderOperationError as exc:
                attempts.append(exc)
    _raise_attempts(attempts)


async def list_mail(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    folder: str,
    offset: int,
    limit: int,
    method: str | None,
) -> MailPageRead:
    account, secrets = await _provider_context(session, account_id)
    if folder == "all":
        results = await asyncio.gather(
            *(
                _list_single_folder(
                    account,
                    secrets,
                    folder=item,
                    offset=offset,
                    limit=limit,
                    method=method,
                )
                for item in ("inbox", "junkemail")
            ),
            return_exceptions=True,
        )
        pages: list[MailPage] = []
        partial_errors: dict[str, object] = {}
        for folder_name, result in zip(("inbox", "junkemail"), results, strict=True):
            if isinstance(result, BaseException):
                partial_errors[folder_name] = str(result)
            else:
                pages.append(result[0])
        if not pages:
            raise ApiProblem(
                status=502,
                code="ALL_FOLDERS_FAILED",
                title="All mail folders failed",
                detail="Inbox and junk mail could not be loaded.",
                context={"folders": partial_errors},
            )
        items = sorted(
            (message for page in pages for message in page.items),
            key=lambda message: message.received_at,
            reverse=True,
        )[:limit]
        selected_method = pages[0].method
        await _record_success(session, account_id, selected_method)
        return MailPageRead(
            items=[MailSummaryRead.model_validate(item) for item in items],
            has_more=any(page.has_more for page in pages),
            method=selected_method,
            partial_errors=partial_errors,
        )

    attempts: list[ProviderOperationError] = []
    for provider in _providers(account, method):
        for account_attempt in proxy_variants(account):
            try:
                page = await provider.list_messages(
                    account_attempt,
                    secrets,
                    folder=folder,
                    offset=offset,
                    limit=limit,
                )
                await _record_success(session, account_id, page.method)
                return MailPageRead(
                    items=[MailSummaryRead.model_validate(item) for item in page.items],
                    has_more=page.has_more,
                    method=page.method,
                )
            except ProviderOperationError as exc:
                attempts.append(exc)
    if _records_account_wide_failure(method):
        await _record_failure(session, account_id, attempts)
    _raise_attempts(attempts)


async def _call_message_operation(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    method: str | None,
    operation: str,
    folder: str,
    message_id: str,
    attachment_id: str | None = None,
) -> tuple[Any, str]:
    account, secrets = await _provider_context(session, account_id)
    attempts: list[ProviderOperationError] = []
    for provider in _providers(account, method):
        for account_attempt in proxy_variants(account):
            try:
                function = getattr(provider, operation)
                kwargs: dict[str, Any] = {
                    "folder": folder,
                    "message_id": message_id,
                }
                if attachment_id is not None:
                    kwargs["attachment_id"] = attachment_id
                result = await function(account_attempt, secrets, **kwargs)
                await _record_success(session, account_id, provider.channel)
                return result, provider.channel
            except ProviderOperationError as exc:
                attempts.append(exc)
    if _records_account_wide_failure(method):
        await _record_failure(session, account_id, attempts)
    _raise_attempts(attempts)


async def get_mail_detail(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    folder: str,
    message_id: str,
    method: str | None,
) -> MailDetailRead:
    detail, selected_method = await _call_message_operation(
        session,
        account_id,
        method=method,
        operation="get_message",
        folder=folder,
        message_id=message_id,
    )
    if not isinstance(detail, MailMessageDetail):
        raise ApiProblem(
            status=502,
            code="MAIL_PROVIDER_RESPONSE_INVALID",
            title="Mail provider returned an invalid response",
            detail="The selected provider did not return a mail message detail.",
        )
    return MailDetailRead.model_validate({**detail.__dict__, "method": selected_method})


async def get_raw_mail(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    folder: str,
    message_id: str,
    method: str | None,
) -> bytes:
    raw, _selected_method = await _call_message_operation(
        session,
        account_id,
        method=method,
        operation="get_raw_message",
        folder=folder,
        message_id=message_id,
    )
    return cast(bytes, raw)


async def download_mail_attachment(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    folder: str,
    message_id: str,
    attachment_id: str,
    method: str | None,
) -> DownloadedAttachment:
    attachment, _selected_method = await _call_message_operation(
        session,
        account_id,
        method=method,
        operation="download_attachment",
        folder=folder,
        message_id=message_id,
        attachment_id=attachment_id,
    )
    return cast(DownloadedAttachment, attachment)


async def mark_mail_read(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    folder: str,
    message_id: str,
    method: str | None,
) -> None:
    await _call_message_operation(
        session,
        account_id,
        method=method,
        operation="mark_read",
        folder=folder,
        message_id=message_id,
    )
    await session.execute(
        update(RetainedMailMessage)
        .where(
            RetainedMailMessage.account_id == account_id,
            RetainedMailMessage.folder == folder,
            RetainedMailMessage.provider_message_id == message_id,
        )
        .values(is_read=True, updated_at=datetime.now(UTC))
    )
    add_audit_log(
        session,
        action="mail.mark_read",
        resource_type="mail_message",
        resource_id=message_id,
        data={"account_id": str(account_id), "folder": folder},
    )
    await session.commit()


async def delete_mail(
    session: AsyncSession,
    account_id: uuid.UUID,
    *,
    folder: str,
    message_id: str,
    method: str | None,
) -> None:
    await _call_message_operation(
        session,
        account_id,
        method=method,
        operation="delete_message",
        folder=folder,
        message_id=message_id,
    )
    await session.execute(
        delete(RetainedMailMessage).where(
            RetainedMailMessage.account_id == account_id,
            RetainedMailMessage.folder == folder,
            RetainedMailMessage.provider_message_id == message_id,
        )
    )
    add_audit_log(
        session,
        action="mail.delete",
        resource_type="mail_message",
        resource_id=message_id,
        data={"account_id": str(account_id), "folder": folder},
    )
    await session.commit()
