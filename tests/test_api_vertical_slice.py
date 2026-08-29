from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from smart_email_manager.config import get_settings
from smart_email_manager.db.models import Account, AccountHealthSnapshot, Job, JobItem
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.jobs import worker
from smart_email_manager.jobs.worker import run_once


async def create_account(email: str = "alpha@example.com") -> uuid.UUID:
    async with get_session_factory()() as session:
        account = Account(
            email=email,
            email_normalized=email.lower(),
            account_type="outlook",
            provider="outlook",
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)
        return account.id


async def test_system_health_and_empty_fleet(api_client: httpx.AsyncClient) -> None:
    health_response = await api_client.get("/api/v1/system/health")
    assert health_response.status_code == 200
    assert health_response.json()["database"] == "ok"

    summary_response = await api_client.get("/api/v1/fleet/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["total_accounts"] == 0


async def test_create_account_rejects_case_insensitive_duplicate(api_client: httpx.AsyncClient) -> None:
    payload = {
        "email": "Automation.Example@outlook.com",
        "account_type": "outlook",
        "provider": "outlook",
        "remark": "created through API",
    }
    created = await api_client.post("/api/v1/accounts", json=payload)
    assert created.status_code == 201
    assert created.json()["email"] == payload["email"]

    summary = await api_client.get("/api/v1/fleet/summary")
    assert summary.json()["needs_attention"] == 1

    payload["email"] = "automation.example@outlook.com"
    duplicate = await api_client.post("/api/v1/accounts", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "ACCOUNT_EMAIL_CONFLICT"


async def test_account_list_and_metadata_health_job(api_client: httpx.AsyncClient) -> None:
    account_id = await create_account()

    accounts_response = await api_client.get("/api/v1/accounts", params={"limit": 100})
    assert accounts_response.status_code == 200
    accounts_payload = accounts_response.json()
    assert accounts_payload["items"][0]["id"] == str(account_id)
    assert accounts_payload["items"][0]["token_status"] == "never"

    create_response = await api_client.post(
        "/api/v1/health-check-jobs",
        headers={"Idempotency-Key": "test-health-job-1"},
        json={"account_ids": [str(account_id)], "limit": 100, "mode": "metadata"},
    )
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    assert await run_once(get_settings()) is True

    job_response = await api_client.get(f"/api/v1/jobs/{job_id}")
    assert job_response.status_code == 200
    job_payload = job_response.json()
    assert job_payload["status"] == "completed"
    assert job_payload["succeeded_count"] == 1

    event_response = await api_client.get(f"/api/v1/jobs/{job_id}/events")
    assert event_response.status_code == 200
    event_types = [item["event_type"] for item in event_response.json()["items"]]
    assert event_types == [
        "job.created",
        "job_item.started",
        "job_item.succeeded",
        "job.finished",
    ]

    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        assert account.mail_health_status == "unknown"
        assert account.health_reason_code == "REMOTE_CHECK_NOT_RUN"
        snapshot_count = len((await session.scalars(AccountHealthSnapshot.__table__.select())).all())
        assert snapshot_count == 1


async def test_idempotency_key_returns_same_job(api_client: httpx.AsyncClient) -> None:
    await create_account()
    payload = {"account_ids": [], "limit": 100, "mode": "metadata"}
    headers = {"Idempotency-Key": "same-job"}
    first = await api_client.post("/api/v1/health-check-jobs", headers=headers, json=payload)
    second = await api_client.post("/api/v1/health-check-jobs", headers=headers, json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]


async def test_expired_terminal_lease_finalizes_job(api_client: httpx.AsyncClient) -> None:
    account_id = await create_account()
    created = await api_client.post(
        "/api/v1/health-check-jobs",
        json={"account_ids": [str(account_id)], "limit": 100, "mode": "metadata"},
    )
    job_id = uuid.UUID(created.json()["id"])

    async with get_session_factory()() as session:
        job = await session.get(Job, job_id)
        item = await session.scalar(select(JobItem).where(JobItem.job_id == job_id))
        assert job is not None and item is not None
        job.status = "running"
        item.status = "running"
        item.attempt_count = item.max_attempts
        item.lease_owner = "dead-worker"
        item.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    assert await run_once(get_settings()) is False

    async with get_session_factory()() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.failed_count == 1


async def test_job_pause_stops_new_leases_and_resume_finishes(
    api_client: httpx.AsyncClient,
) -> None:
    account_id = await create_account("pause@example.com")
    created = await api_client.post(
        "/api/v1/health-check-jobs",
        json={"account_ids": [str(account_id)], "limit": 1, "mode": "metadata"},
    )
    job_id = created.json()["id"]
    pause = await api_client.post(f"/api/v1/jobs/{job_id}/pause")
    assert pause.status_code == 202
    assert pause.json()["status"] == "pausing"
    assert await run_once(get_settings()) is False
    paused = await api_client.get(f"/api/v1/jobs/{job_id}")
    assert paused.json()["status"] == "paused"
    resume = await api_client.post(f"/api/v1/jobs/{job_id}/resume")
    assert resume.status_code == 202
    assert resume.json()["status"] == "queued"
    assert await run_once(get_settings()) is True
    finished = await api_client.get(f"/api/v1/jobs/{job_id}")
    assert finished.json()["status"] == "completed"


async def test_unhandled_worker_error_retries_then_succeeds(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = await create_account("retry@example.com")
    created = await api_client.post(
        "/api/v1/health-check-jobs",
        json={"account_ids": [str(account_id)], "limit": 1, "mode": "metadata"},
    )
    job_id = uuid.UUID(created.json()["id"])
    original_handler = worker.HANDLERS["account.health_check"]

    async def explode(_session: object, _lease: object) -> None:
        raise RuntimeError("transient worker failure")

    monkeypatch.setitem(worker.HANDLERS, "account.health_check", explode)
    assert await run_once(get_settings()) is True
    async with get_session_factory()() as session:
        job = await session.get(Job, job_id)
        item = await session.scalar(select(JobItem).where(JobItem.job_id == job_id))
        assert job is not None and item is not None
        assert job.status == "running"
        assert item.status == "retry_wait"
        assert item.attempt_count == 1
        assert item.run_after is not None and item.run_after > datetime.now(UTC)
        item.run_after = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    monkeypatch.setitem(worker.HANDLERS, "account.health_check", original_handler)
    assert await run_once(get_settings()) is True
    async with get_session_factory()() as session:
        job = await session.get(Job, job_id)
        item = await session.scalar(select(JobItem).where(JobItem.job_id == job_id))
        assert job is not None and item is not None
        assert job.status == "completed"
        assert item.status == "succeeded"
        assert item.attempt_count == 2
    events = await api_client.get(f"/api/v1/jobs/{job_id}/events")
    assert "job_item.retry_scheduled" in {
        event["event_type"] for event in events.json()["items"]
    }
