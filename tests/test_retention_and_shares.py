from __future__ import annotations

import hashlib
import uuid

import httpx
import pytest
from sqlalchemy import select

from smart_email_manager.api.schemas.mail import (
    MailAttachmentRead,
    MailDetailRead,
    MailPageRead,
    MailSummaryRead,
)
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import EmailShareLink, Job, RetainedMailMessage
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.jobs.worker import run_once
from smart_email_manager.services import retention
from smart_email_manager.services.retention import cache_mail_detail, cache_mail_page


async def _create_account(api_client: httpx.AsyncClient, email: str) -> uuid.UUID:
    response = await api_client.post(
        "/api/v1/accounts",
        json={"email": email, "provider": "outlook"},
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _mail_page() -> MailPageRead:
    return MailPageRead(
        items=[
            MailSummaryRead(
                id="message-1",
                folder="inbox",
                subject="Retained subject",
                sender="sender@example.com",
                recipients=["recipient@example.com"],
                received_at="2026-08-28T10:00:00Z",
                is_read=False,
                has_attachments=True,
                body_preview="Retained preview",
                id_mode="graph",
            )
        ],
        has_more=False,
        method="graph",
    )


def _mail_detail() -> MailDetailRead:
    return MailDetailRead(
        id="message-1",
        folder="inbox",
        subject="Retained subject",
        sender="sender@example.com",
        recipients=["recipient@example.com"],
        cc=[],
        received_at="2026-08-28T10:00:00Z",
        is_read=False,
        body="retained body",
        body_type="text",
        attachments=[
            MailAttachmentRead(
                id="attachment-1",
                name="proof.txt",
                content_type="text/plain",
                size=5,
                is_inline=False,
            )
        ],
        id_mode="graph",
        method="graph",
    )


async def test_retained_mail_and_hashed_share_public_read_path(
    api_client: httpx.AsyncClient,
) -> None:
    account_id = await _create_account(api_client, "shared-retained@example.com")
    policy = await api_client.put(
        f"/api/v1/retention/accounts/{account_id}/policy",
        json={
            "enabled": True,
            "retain_bodies": True,
            "folders": ["inbox"],
            "max_messages": 100,
            "max_age_days": 30,
        },
    )
    assert policy.status_code == 200
    async with get_session_factory()() as session:
        assert await cache_mail_page(session, account_id=account_id, page=_mail_page()) == 1
        await cache_mail_detail(session, account_id=account_id, detail=_mail_detail())

    cached = await api_client.get(f"/api/v1/retention/accounts/{account_id}/mail")
    cached_detail = await api_client.get(f"/api/v1/retention/accounts/{account_id}/mail/message-1")
    stats = await api_client.get("/api/v1/retention/stats")
    assert cached.json()["items"][0]["subject"] == "Retained subject"
    assert cached_detail.json()["body"] == "retained body"
    assert stats.json()["message_count"] == 1
    assert stats.json()["body_count"] == 1

    created = await api_client.post(
        "/api/v1/email-shares",
        json={
            "account_id": str(account_id),
            "never_expires": True,
            "allowed_folders": ["inbox"],
        },
    )
    assert created.status_code == 201
    payload = created.json()
    token = payload["token"]
    share_id = uuid.UUID(payload["id"])
    assert token.startswith("sem_share_")
    assert payload["share_path"].endswith(token)

    listed = await api_client.get("/api/v1/email-shares")
    assert listed.status_code == 200
    assert "token" not in listed.json()[0]
    async with get_session_factory()() as session:
        link = await session.get(EmailShareLink, share_id)
        assert link is not None
        assert link.token_hash == hashlib.sha256(token.encode()).digest()
        assert token.encode() not in link.token_hash

    public_status = await api_client.get(f"/api/v1/public/email-shares/{token}/status")
    public_mail = await api_client.get(
        f"/api/v1/public/email-shares/{token}/mail",
        params={"source": "retained"},
    )
    public_detail = await api_client.get(
        f"/api/v1/public/email-shares/{token}/mail/message-1",
        params={"source": "retained"},
    )
    forbidden = await api_client.get(
        f"/api/v1/public/email-shares/{token}/mail",
        params={"folder": "junkemail", "source": "retained"},
    )
    assert public_status.json()["email"] == "shared-retained@example.com"
    assert public_mail.json()["items"][0]["id"] == "message-1"
    assert public_detail.json()["body"] == "retained body"
    assert forbidden.status_code == 403

    revoked = await api_client.post(f"/api/v1/email-shares/{share_id}/revoke")
    after_revoke = await api_client.get(f"/api/v1/public/email-shares/{token}/status")
    assert revoked.json()["status"] == "revoked"
    assert after_revoke.status_code == 410


async def test_retention_sync_job_fetches_and_prunes_through_worker(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = await _create_account(api_client, "retention-worker@example.com")
    await api_client.put(
        f"/api/v1/retention/accounts/{account_id}/policy",
        json={
            "enabled": True,
            "retain_bodies": True,
            "folders": ["inbox"],
            "max_messages": 10,
            "max_age_days": 30,
        },
    )

    async def fake_list_mail(*_args: object, **_kwargs: object) -> MailPageRead:
        return _mail_page()

    async def fake_get_detail(*_args: object, **_kwargs: object) -> MailDetailRead:
        return _mail_detail()

    monkeypatch.setattr(retention, "list_mail", fake_list_mail)
    monkeypatch.setattr(retention, "get_mail_detail", fake_get_detail)
    response = await api_client.post(
        "/api/v1/retention/sync-jobs",
        json={"account_ids": [str(account_id)], "limit": 1},
    )
    assert response.status_code == 202
    job_id = uuid.UUID(response.json()["id"])
    assert await run_once(get_settings()) is True

    async with get_session_factory()() as session:
        job = await session.get(Job, job_id)
        retained = await session.scalar(
            select(RetainedMailMessage).where(RetainedMailMessage.account_id == account_id)
        )
        assert job is not None and retained is not None
        assert job.status == "completed"
        assert retained.body == "retained body"
