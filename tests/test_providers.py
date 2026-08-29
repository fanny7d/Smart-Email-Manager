from __future__ import annotations

import imaplib
import uuid
from email.message import EmailMessage

import httpx
import pytest

from smart_email_manager.config import get_settings
from smart_email_manager.db.models import Account
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.jobs import handlers
from smart_email_manager.jobs.worker import run_once
from smart_email_manager.providers.base import ProviderAccount, ProviderHealthResult
from smart_email_manager.providers.graph import GraphProvider
from smart_email_manager.providers.imap import _imap_failure, parse_message_detail
from smart_email_manager.services.secrets import DecryptedAccountSecrets


async def test_graph_provider_health_uses_refresh_token_without_exposing_it() -> None:
    requests: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "short-lived-access"})
        return httpx.Response(200, json={"id": "user-id", "mail": "graph@example.com"})

    provider = GraphProvider(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport))
    )
    result = await provider.check_health(
        ProviderAccount(
            id=uuid.uuid4(),
            email="graph@example.com",
            account_type="outlook",
            provider="outlook",
            authorization_type="graph",
            provider_metadata={"client_id": "11111111-2222-3333-4444-555555555555"},
        ),
        DecryptedAccountSecrets(refresh_token="never-log-this-refresh-token"),
    )
    assert result.status == "healthy"
    assert result.reason_code == "GRAPH_OK"
    assert len(requests) == 2
    assert "never-log-this-refresh-token" not in repr(result)


async def test_graph_provider_mail_operations() -> None:
    operations: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        operations.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "access"})
        if request.url.path.endswith("/mailFolders/inbox/messages"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "message-id",
                            "subject": "Hello",
                            "from": {"emailAddress": {"address": "sender@example.com"}},
                            "toRecipients": [{"emailAddress": {"address": "recipient@example.com"}}],
                            "receivedDateTime": "2026-08-28T10:00:00Z",
                            "isRead": False,
                            "hasAttachments": True,
                            "bodyPreview": "Preview",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/messages/message-id/attachments/attachment-id"):
            return httpx.Response(
                200,
                json={
                    "id": "attachment-id",
                    "name": "hello.txt",
                    "contentType": "text/plain",
                    "contentBytes": "aGVsbG8=",
                },
            )
        if request.url.path.endswith("/messages/message-id/attachments"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "attachment-id",
                            "name": "hello.txt",
                            "contentType": "text/plain",
                            "size": 5,
                            "isInline": False,
                        }
                    ]
                },
            )
        if request.url.path.endswith("/messages/message-id/$value"):
            return httpx.Response(200, content=b"From: sender@example.com\r\n\r\nbody")
        if request.method == "GET" and request.url.path.endswith("/messages/message-id"):
            return httpx.Response(
                200,
                json={
                    "id": "message-id",
                    "subject": "Hello",
                    "from": {"emailAddress": {"address": "sender@example.com"}},
                    "toRecipients": [{"emailAddress": {"address": "recipient@example.com"}}],
                    "ccRecipients": [],
                    "receivedDateTime": "2026-08-28T10:00:00Z",
                    "isRead": False,
                    "body": {"contentType": "html", "content": "<p>Hello</p>"},
                },
            )
        if request.method == "PATCH":
            return httpx.Response(200, json={"isRead": True})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, json={"error": {"message": "unexpected"}})

    provider = GraphProvider(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport))
    )
    account = ProviderAccount(
        id=uuid.uuid4(),
        email="graph@example.com",
        account_type="outlook",
        provider="outlook",
        authorization_type="graph",
        provider_metadata={"client_id": "11111111-2222-3333-4444-555555555555"},
    )
    secrets = DecryptedAccountSecrets(refresh_token="refresh")
    page = await provider.list_messages(account, secrets, folder="inbox", offset=0, limit=20)
    detail = await provider.get_message(account, secrets, folder="inbox", message_id="message-id")
    raw = await provider.get_raw_message(account, secrets, folder="inbox", message_id="message-id")
    attachment = await provider.download_attachment(
        account,
        secrets,
        folder="inbox",
        message_id="message-id",
        attachment_id="attachment-id",
    )
    await provider.mark_read(account, secrets, folder="inbox", message_id="message-id")
    await provider.delete_message(account, secrets, folder="inbox", message_id="message-id")

    assert page.items[0].subject == "Hello"
    assert detail.body == "<p>Hello</p>"
    assert detail.attachments[0].name == "hello.txt"
    assert raw.endswith(b"body")
    assert attachment.content == b"hello"
    assert any(item.startswith("PATCH ") for item in operations)
    assert any(item.startswith("DELETE ") for item in operations)


def test_imap_mime_parser_preserves_html_and_attachments() -> None:
    message = EmailMessage()
    message["Subject"] = "MIME test"
    message["From"] = "sender@example.com"
    message["To"] = "recipient@example.com"
    message.set_content("plain body")
    message.add_alternative("<p>html body</p>", subtype="html")
    message.add_attachment(b"attachment", maintype="application", subtype="octet-stream", filename="a.bin")

    detail = parse_message_detail(message.as_bytes(), message_id="12", folder="inbox")
    assert detail.body_type == "html"
    assert "html body" in detail.body
    assert detail.attachments[0].id == "1"
    assert detail.attachments[0].size == len(b"attachment")


def test_imap_authenticated_without_session_is_retryable_and_specific() -> None:
    failure = _imap_failure(
        "IMAP_MAIL_LIST_FAILED",
        imaplib.IMAP4.error("User is authenticated but not connected."),
    )
    assert failure.code == "IMAP_SESSION_NOT_CONNECTED"
    assert failure.status == 503
    assert failure.retryable is True
    assert failure.details == {"operation_code": "IMAP_MAIL_LIST_FAILED"}


class HealthyFakeRegistry:
    async def check_health(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ProviderHealthResult:
        assert account.email == "connectivity@example.com"
        assert secrets.refresh_token == "connectivity-refresh-token"
        return ProviderHealthResult(
            status="healthy",
            channel="graph",
            reason_code="GRAPH_OK",
        )


class MixedFailureFakeRegistry:
    async def check_health(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> ProviderHealthResult:
        del account, secrets
        return ProviderHealthResult(
            status="failed",
            channel="all",
            reason_code="ALL_PROVIDER_CHANNELS_FAILED",
            details={
                "attempts": [
                    {
                        "channel": "imap",
                        "reason_code": "IMAP_SESSION_NOT_CONNECTED",
                        "message": "transient session failure",
                    },
                    {
                        "channel": "graph",
                        "reason_code": "GRAPH_TOKEN_REJECTED",
                        "message": "Graph permission missing",
                    },
                ]
            },
        )


async def test_connectivity_job_updates_independent_health_dimensions(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await api_client.post(
        "/api/v1/accounts",
        json={"email": "connectivity@example.com", "provider": "outlook"},
    )
    account_id = uuid.UUID(created.json()["id"])
    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        account.provider_metadata = {"client_id": "11111111-2222-3333-4444-555555555555"}
        await session.commit()
    secrets_response = await api_client.put(
        f"/api/v1/accounts/{account_id}/secrets",
        json={"refresh_token": "connectivity-refresh-token"},
    )
    assert secrets_response.status_code == 200

    monkeypatch.setattr(handlers, "PROVIDER_REGISTRY", HealthyFakeRegistry())
    job_response = await api_client.post(
        "/api/v1/health-check-jobs",
        json={"account_ids": [str(account_id)], "limit": 1, "mode": "connectivity"},
    )
    assert job_response.status_code == 202
    assert await run_once(get_settings()) is True

    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        assert account.mail_health_status == "healthy"
        assert account.authorization_status == "valid"
        assert account.token_status == "success"
        assert account.authorization_type == "graph"
        assert account.consecutive_failures == 0


async def test_missing_provider_credentials_are_classified_without_network(
    api_client: httpx.AsyncClient,
) -> None:
    created = await api_client.post(
        "/api/v1/accounts",
        json={"email": "missing-creds@example.com", "provider": "outlook"},
    )
    account_id = uuid.UUID(created.json()["id"])
    job_response = await api_client.post(
        "/api/v1/health-check-jobs",
        json={"account_ids": [str(account_id)], "limit": 1, "mode": "connectivity"},
    )
    assert job_response.status_code == 202
    assert await run_once(get_settings()) is True

    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        assert account.mail_health_status == "failed"
        assert account.authorization_status == "invalid"
        assert account.token_status == "failed"


async def test_mixed_transient_and_optional_token_failure_does_not_invalidate_authorization(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await api_client.post(
        "/api/v1/accounts",
        json={"email": "mixed-provider-failure@example.com", "provider": "outlook"},
    )
    account_id = uuid.UUID(created.json()["id"])
    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        account.authorization_status = "valid"
        account.token_status = "success"
        await session.commit()
    monkeypatch.setattr(handlers, "PROVIDER_REGISTRY", MixedFailureFakeRegistry())
    job_response = await api_client.post(
        "/api/v1/health-check-jobs",
        json={"account_ids": [str(account_id)], "limit": 1, "mode": "connectivity"},
    )
    assert job_response.status_code == 202
    assert await run_once(get_settings()) is True

    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        assert account.mail_health_status == "failed"
        assert account.authorization_status == "valid"
        assert account.token_status == "success"
