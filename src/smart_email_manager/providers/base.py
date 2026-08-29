from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from smart_email_manager.services.secrets import DecryptedAccountSecrets


@dataclass(frozen=True)
class ProviderAccount:
    id: uuid.UUID
    email: str
    account_type: str
    provider: str
    authorization_type: str
    provider_metadata: dict[str, Any]
    proxy_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderHealthResult:
    status: str
    channel: str
    reason_code: str
    message: str = ""
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "healthy"


@dataclass(frozen=True)
class TokenRefreshResult:
    success: bool
    channel: str
    reason_code: str
    rotated_refresh_token: str | None = None
    message: str = ""
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MailAttachment:
    id: str
    name: str
    content_type: str
    size: int
    is_inline: bool = False


@dataclass(frozen=True)
class MailMessageSummary:
    id: str
    folder: str
    subject: str
    sender: str
    recipients: list[str]
    received_at: str
    is_read: bool
    has_attachments: bool
    body_preview: str
    id_mode: str


@dataclass(frozen=True)
class MailMessageDetail:
    id: str
    folder: str
    subject: str
    sender: str
    recipients: list[str]
    cc: list[str]
    received_at: str
    is_read: bool
    body: str
    body_type: str
    attachments: list[MailAttachment]
    id_mode: str


@dataclass(frozen=True)
class MailPage:
    items: list[MailMessageSummary]
    has_more: bool
    method: str


@dataclass(frozen=True)
class DownloadedAttachment:
    name: str
    content_type: str
    content: bytes


class ProviderOperationError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status: int = 502,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.details = details or {}


class MailProvider(Protocol):
    channel: str

    async def check_health(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ProviderHealthResult: ...

    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult: ...

    async def list_messages(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        offset: int,
        limit: int,
    ) -> MailPage: ...

    async def get_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> MailMessageDetail: ...

    async def get_raw_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> bytes: ...

    async def download_attachment(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
        attachment_id: str,
    ) -> DownloadedAttachment: ...

    async def mark_read(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> None: ...

    async def delete_message(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
        *,
        folder: str,
        message_id: str,
    ) -> None: ...
