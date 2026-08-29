from __future__ import annotations

import uuid

import httpx

from smart_email_manager.db.models import Account
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.providers.base import (
    DownloadedAttachment,
    MailAttachment,
    MailMessageDetail,
    MailMessageSummary,
    MailPage,
    ProviderAccount,
    ProviderHealthResult,
    ProviderOperationError,
)
from smart_email_manager.services import mail as mail_service
from smart_email_manager.services.secrets import DecryptedAccountSecrets


class FakeMailProvider:
    channel = "graph"

    async def check_health(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ProviderHealthResult:
        return ProviderHealthResult("healthy", self.channel, "OK")

    async def list_messages(self, *_args: object, folder: str, **_kwargs: object) -> MailPage:
        return MailPage(
            items=[
                MailMessageSummary(
                    id="m1",
                    folder=folder,
                    subject="API message",
                    sender="sender@example.com",
                    recipients=["recipient@example.com"],
                    received_at="2026-08-28T10:00:00Z",
                    is_read=False,
                    has_attachments=True,
                    body_preview="preview",
                    id_mode="graph",
                )
            ],
            has_more=False,
            method=self.channel,
        )

    async def get_message(self, *_args: object, folder: str, **_kwargs: object) -> MailMessageDetail:
        return MailMessageDetail(
            id="m1",
            folder=folder,
            subject="API message",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            cc=[],
            received_at="2026-08-28T10:00:00Z",
            is_read=False,
            body="body",
            body_type="text",
            attachments=[MailAttachment("a1", "a.txt", "text/plain", 1)],
            id_mode="graph",
        )

    async def get_raw_message(self, *_args: object, **_kwargs: object) -> bytes:
        return b"From: sender@example.com\r\n\r\nbody"

    async def download_attachment(self, *_args: object, **_kwargs: object) -> DownloadedAttachment:
        return DownloadedAttachment("a.txt", "text/plain", b"a")

    async def mark_read(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def delete_message(self, *_args: object, **_kwargs: object) -> None:
        return None


class FakeMailRegistry:
    def __init__(self) -> None:
        self.provider = FakeMailProvider()

    def ordered_providers(
        self,
        account: ProviderAccount,
        requested_method: str | None = None,
    ) -> list[FakeMailProvider]:
        del account, requested_method
        return [self.provider]


class FailingMailProvider(FakeMailProvider):
    async def list_messages(self, *_args: object, **_kwargs: object) -> MailPage:
        raise ProviderOperationError(
            code="GRAPH_TOKEN_REJECTED",
            message="No applicable permissions were found for this user.",
            status=400,
        )


class FailingMailRegistry(FakeMailRegistry):
    def __init__(self) -> None:
        self.provider = FailingMailProvider()


async def test_mail_api_read_and_write_paths(
    api_client: httpx.AsyncClient,
    monkeypatch: object,
) -> None:
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setattr(mail_service, "MAIL_REGISTRY", FakeMailRegistry())
    created = await api_client.post(
        "/api/v1/accounts",
        json={"email": "mail-api@example.com", "provider": "outlook"},
    )
    account_id = uuid.UUID(created.json()["id"])

    page = await api_client.get(f"/api/v1/accounts/{account_id}/mail")
    assert page.status_code == 200
    assert page.json()["items"][0]["subject"] == "API message"

    detail = await api_client.get(f"/api/v1/accounts/{account_id}/mail/messages/m1")
    assert detail.status_code == 200
    assert detail.json()["method"] == "graph"

    raw = await api_client.get(f"/api/v1/accounts/{account_id}/mail/messages/m1/raw")
    assert raw.status_code == 200
    assert raw.headers["content-type"].startswith("message/rfc822")

    attachment = await api_client.get(f"/api/v1/accounts/{account_id}/mail/messages/m1/attachments/a1")
    assert attachment.content == b"a"

    assert (await api_client.post(f"/api/v1/accounts/{account_id}/mail/messages/m1/read")).status_code == 204
    assert (await api_client.delete(f"/api/v1/accounts/{account_id}/mail/messages/m1")).status_code == 204


async def test_explicit_provider_failure_does_not_overwrite_account_wide_health(
    api_client: httpx.AsyncClient,
    monkeypatch: object,
) -> None:
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setattr(mail_service, "MAIL_REGISTRY", FailingMailRegistry())
    created = await api_client.post(
        "/api/v1/accounts",
        json={"email": "provider-diagnostic@example.com", "provider": "outlook"},
    )
    account_id = uuid.UUID(created.json()["id"])
    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        account.mail_health_status = "healthy"
        account.health_reason_code = "IMAP_OK"
        await session.commit()

    explicit = await api_client.get(
        f"/api/v1/accounts/{account_id}/mail",
        params={"method": "graph"},
    )
    assert explicit.status_code == 400
    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        assert account.mail_health_status == "healthy"
        assert account.health_reason_code == "IMAP_OK"

    automatic = await api_client.get(
        f"/api/v1/accounts/{account_id}/mail",
        params={"method": "auto"},
    )
    assert automatic.status_code == 400
    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        assert account.mail_health_status == "failed"
        assert account.health_reason_code == "ALL_PROVIDER_CHANNELS_FAILED"
