from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from smart_email_manager.api.schemas.mail import MailDetailRead, MailPageRead, MailSummaryRead
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import (
    AccountForwarding,
    ForwardingDelivery,
    ForwardingDestination,
    Job,
)
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.jobs.worker import run_once
from smart_email_manager.providers.forwarding import (
    ForwardingSender,
    ForwardPayload,
    ForwardResult,
)
from smart_email_manager.services import forwarding


class SuccessfulSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def send(
        self,
        *,
        channel: str,
        config: dict[str, object],
        secret: str,
        payload: ForwardPayload,
    ) -> ForwardResult:
        self.calls.append((channel, secret, payload.subject))
        assert config["host"] == "smtp.example.test"
        return ForwardResult(True, channel, "SMTP_SENT")


def _page() -> MailPageRead:
    return MailPageRead(
        items=[
            MailSummaryRead(
                id="forward-message-1",
                folder="inbox",
                subject="Forward this",
                sender="sender@example.com",
                recipients=["recipient@example.com"],
                received_at="2026-08-28T20:00:00Z",
                is_read=False,
                has_attachments=False,
                body_preview="preview",
                id_mode="graph",
            )
        ],
        has_more=False,
        method="graph",
    )


def _detail() -> MailDetailRead:
    return MailDetailRead(
        id="forward-message-1",
        folder="inbox",
        subject="Forward this",
        sender="sender@example.com",
        recipients=["recipient@example.com"],
        cc=[],
        received_at="2026-08-28T20:00:00Z",
        is_read=False,
        body="forwarding body",
        body_type="text",
        attachments=[],
        id_mode="graph",
        method="graph",
    )


async def test_forwarding_job_encrypts_destination_deduplicates_and_advances_cursor(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_response = await api_client.post(
        "/api/v1/accounts",
        json={"email": "forwarding@example.com", "provider": "outlook"},
    )
    account_id = uuid.UUID(account_response.json()["id"])
    destination_response = await api_client.post(
        "/api/v1/forwarding/destinations",
        json={
            "name": "smtp-main",
            "channel": "smtp",
            "config": {"host": "smtp.example.test", "recipient": "target@example.test"},
            "secret": "smtp-secret-password",
        },
    )
    assert destination_response.status_code == 201
    assert "secret" not in destination_response.json()
    destination_id = uuid.UUID(destination_response.json()["id"])
    configured = await api_client.put(
        f"/api/v1/forwarding/accounts/{account_id}",
        json={
            "enabled": True,
            "include_junk": False,
            "window_minutes": 0,
            "destination_ids": [str(destination_id)],
        },
    )
    assert configured.status_code == 200

    async with get_session_factory()() as session:
        destination = await session.get(ForwardingDestination, destination_id)
        assert destination is not None
        assert b"smtp-secret-password" not in destination.secret_ciphertext

    async def fake_list(*_args: object, **_kwargs: object) -> MailPageRead:
        return _page()

    async def fake_detail(*_args: object, **_kwargs: object) -> MailDetailRead:
        return _detail()

    sender = SuccessfulSender()
    monkeypatch.setattr(forwarding, "list_mail", fake_list)
    monkeypatch.setattr(forwarding, "get_mail_detail", fake_detail)
    monkeypatch.setattr(forwarding, "FORWARDING_SENDER", sender)

    first_job = await api_client.post(
        "/api/v1/forwarding/jobs",
        json={"account_ids": [str(account_id)], "limit": 1},
    )
    first_job_id = uuid.UUID(first_job.json()["id"])
    assert await run_once(get_settings()) is True
    second_job = await api_client.post(
        "/api/v1/forwarding/jobs",
        json={"account_ids": [str(account_id)], "limit": 1},
    )
    assert await run_once(get_settings()) is True

    async with get_session_factory()() as session:
        job = await session.get(Job, first_job_id)
        config = await session.get(AccountForwarding, account_id)
        deliveries = list(
            (
                await session.scalars(
                    select(ForwardingDelivery).where(ForwardingDelivery.account_id == account_id)
                )
            ).all()
        )
        assert job is not None and config is not None
        assert job.status == "completed"
        assert config.cursor_at is not None
        assert len(deliveries) == 1
        assert deliveries[0].status == "success"
        assert deliveries[0].attempt_count == 1
    assert second_job.status_code == 202
    assert sender.calls == [("smtp", "smtp-secret-password", "[forwarding@example.com] Forward this")]
    history = await api_client.get(
        "/api/v1/forwarding/deliveries",
        params={"account_id": str(account_id)},
    )
    assert history.json()[0]["status"] == "success"


async def test_non_smtp_forwarding_sender_is_not_supported() -> None:
    sender = ForwardingSender()
    payload = ForwardPayload(subject="test", text="body")
    result = await sender.send(
        channel="telegram",
        config={},
        secret="unused",
        payload=payload,
    )
    assert result.success is False
    assert result.reason_code == "FORWARD_CHANNEL_UNSUPPORTED"
