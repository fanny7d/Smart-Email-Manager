from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import (
    Account,
    AccountSecret,
    Job,
    JobItem,
    Schedule,
    TokenRefreshLog,
)
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.jobs import handlers
from smart_email_manager.jobs.worker import run_once
from smart_email_manager.providers.base import ProviderAccount, TokenRefreshResult
from smart_email_manager.providers.graph import GraphProvider
from smart_email_manager.providers.imap import ImapProvider
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.schedules import next_schedule_run, run_due_schedules
from smart_email_manager.services.secrets import DecryptedAccountSecrets


class SuccessfulRefreshRegistry:
    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult:
        assert account.email == "refresh-success@example.com"
        assert secrets.refresh_token == "old-refresh-token"
        return TokenRefreshResult(
            True,
            "graph",
            "GRAPH_TOKEN_REFRESHED",
            rotated_refresh_token="rotated-refresh-token",
            details={"expires_in": 3600},
        )


class FailedRefreshRegistry:
    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult:
        assert secrets.refresh_token == "rejected-refresh-token"
        return TokenRefreshResult(
            False,
            "all",
            "ALL_TOKEN_REFRESH_CHANNELS_FAILED",
            message="The provider rejected the refresh token.",
            retryable=False,
        )


class ScheduledRefreshRegistry:
    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult:
        assert account.email == "scheduled@example.com"
        return TokenRefreshResult(True, "graph", "GRAPH_TOKEN_REFRESHED")


class FlakyRefreshRegistry:
    def __init__(self) -> None:
        self.calls = 0

    async def refresh_authorization(
        self,
        account: ProviderAccount,
        secrets: DecryptedAccountSecrets,
    ) -> TokenRefreshResult:
        del account, secrets
        self.calls += 1
        if self.calls == 1:
            return TokenRefreshResult(
                False,
                "graph",
                "GRAPH_NETWORK_FAILED",
                message="temporary network failure",
                retryable=True,
            )
        return TokenRefreshResult(True, "graph", "GRAPH_TOKEN_REFRESHED")


async def _create_refreshable_account(
    api_client: httpx.AsyncClient,
    *,
    email: str,
    refresh_token: str,
) -> uuid.UUID:
    created = await api_client.post(
        "/api/v1/accounts",
        json={"email": email, "provider": "outlook"},
    )
    assert created.status_code == 201
    account_id = uuid.UUID(created.json()["id"])
    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        assert account is not None
        account.provider_metadata = {"client_id": "11111111-2222-3333-4444-555555555555"}
        await session.commit()
    secret_response = await api_client.put(
        f"/api/v1/accounts/{account_id}/secrets",
        json={"refresh_token": refresh_token},
    )
    assert secret_response.status_code == 200
    return account_id


async def test_token_refresh_job_rotates_encrypted_secret_and_records_log(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = await _create_refreshable_account(
        api_client,
        email="refresh-success@example.com",
        refresh_token="old-refresh-token",
    )
    monkeypatch.setattr(handlers, "PROVIDER_REGISTRY", SuccessfulRefreshRegistry())

    response = await api_client.post(
        "/api/v1/token-refresh-jobs",
        json={"account_ids": [str(account_id)], "limit": 1},
    )
    assert response.status_code == 202
    job_id = uuid.UUID(response.json()["id"])
    assert await run_once(get_settings()) is True

    cipher = AccountSecretCipher.from_settings(get_settings())
    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        secret = await session.get(AccountSecret, account_id)
        job = await session.get(Job, job_id)
        log = await session.scalar(select(TokenRefreshLog).where(TokenRefreshLog.account_id == account_id))
        assert account is not None and secret is not None and job is not None and log is not None
        assert account.token_status == "success"
        assert account.authorization_status == "valid"
        assert account.authorization_type == "graph"
        assert job.status == "completed"
        assert log.status == "success"
        assert log.rotated is True
        assert secret.refresh_token_ciphertext is not None
        assert (
            cipher.decrypt(
                account_id,
                "refresh_token",
                secret.refresh_token_ciphertext,
                secret.key_version,
            )
            == "rotated-refresh-token"
        )

    summary = await api_client.get("/api/v1/token-refresh-summary")
    logs = await api_client.get(
        "/api/v1/token-refresh-logs",
        params={"account_id": str(account_id)},
    )
    assert summary.json() == {
        "total_refreshable": 1,
        "never": 0,
        "success": 1,
        "failed": 0,
        "stale": 0,
    }
    assert logs.json()[0]["job_id"] == str(job_id)


async def test_token_refresh_failure_marks_job_and_authorization(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = await _create_refreshable_account(
        api_client,
        email="refresh-failed@example.com",
        refresh_token="rejected-refresh-token",
    )
    monkeypatch.setattr(handlers, "PROVIDER_REGISTRY", FailedRefreshRegistry())
    response = await api_client.post(
        "/api/v1/token-refresh-jobs",
        json={"account_ids": [str(account_id)], "limit": 1},
    )
    job_id = uuid.UUID(response.json()["id"])
    assert await run_once(get_settings()) is True

    async with get_session_factory()() as session:
        account = await session.get(Account, account_id)
        job = await session.get(Job, job_id)
        log = await session.scalar(select(TokenRefreshLog).where(TokenRefreshLog.account_id == account_id))
        assert account is not None and job is not None and log is not None
        assert account.token_status == "failed"
        assert account.authorization_status == "reauthorization_required"
        assert job.status == "failed"
        assert log.status == "failed"
        assert log.error_summary == "The provider rejected the refresh token."


async def test_retryable_token_refresh_uses_retry_wait_then_completes(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_id = await _create_refreshable_account(
        api_client,
        email="refresh-retry@example.com",
        refresh_token="retry-refresh-token",
    )
    registry = FlakyRefreshRegistry()
    monkeypatch.setattr(handlers, "PROVIDER_REGISTRY", registry)
    response = await api_client.post(
        "/api/v1/token-refresh-jobs",
        json={"account_ids": [str(account_id)], "limit": 1},
    )
    job_id = uuid.UUID(response.json()["id"])
    assert await run_once(get_settings()) is True
    async with get_session_factory()() as session:
        job = await session.get(Job, job_id)
        item = await session.scalar(select(JobItem).where(JobItem.job_id == job_id))
        assert job is not None and item is not None
        assert job.status == "running"
        assert item.status == "retry_wait"
        assert item.error_code == "GRAPH_NETWORK_FAILED"
        item.run_after = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert await run_once(get_settings()) is True
    async with get_session_factory()() as session:
        job = await session.get(Job, job_id)
        account = await session.get(Account, account_id)
        logs = list(
            (
                await session.scalars(
                    select(TokenRefreshLog).where(
                        TokenRefreshLog.account_id == account_id
                    )
                )
            ).all()
        )
        assert job is not None and account is not None
        assert job.status == "completed"
        assert account.token_status == "success"
        assert registry.calls == 2
        assert [log.status for log in logs] == ["failed", "success"]


async def test_due_schedule_creates_exactly_one_job_and_advances(
    api_client: httpx.AsyncClient,
) -> None:
    account_id = await _create_refreshable_account(
        api_client,
        email="scheduled@example.com",
        refresh_token="scheduled-refresh-token",
    )
    created = await api_client.post(
        "/api/v1/schedules",
        json={
            "name": "every-minute-refresh",
            "task_type": "token_refresh",
            "cron_expression": "* * * * *",
            "timezone": "Asia/Shanghai",
            "payload": {"account_ids": [str(account_id)], "limit": 1},
        },
    )
    assert created.status_code == 201
    schedule_id = uuid.UUID(created.json()["id"])
    due_at = datetime.now(UTC) - timedelta(minutes=1)
    async with get_session_factory()() as session:
        schedule = await session.get(Schedule, schedule_id)
        assert schedule is not None
        schedule.next_run_at = due_at
        await session.commit()

    async with get_session_factory()() as session:
        assert await run_due_schedules(session, now=datetime.now(UTC)) == 1
    async with get_session_factory()() as session:
        assert await run_due_schedules(session, now=datetime.now(UTC)) == 0
        schedule = await session.get(Schedule, schedule_id)
        assert schedule is not None
        assert schedule.last_job_id is not None
        assert schedule.next_run_at > datetime.now(UTC)
        job = await session.get(Job, schedule.last_job_id)
        assert job is not None
        assert job.job_type == "account.token_refresh"
        assert job.total_count == 1


async def test_schedule_validation_reports_cron_and_timezone_problems(
    api_client: httpx.AsyncClient,
) -> None:
    bad_cron = await api_client.post(
        "/api/v1/schedules",
        json={
            "name": "bad-cron",
            "cron_expression": "not a cron",
            "payload": {},
        },
    )
    bad_timezone = await api_client.post(
        "/api/v1/schedules",
        json={
            "name": "bad-timezone",
            "cron_expression": "0 * * * *",
            "timezone": "Mars/Olympus",
            "payload": {},
        },
    )
    assert bad_cron.status_code == 422
    assert bad_cron.json()["code"] == "SCHEDULE_CRON_INVALID"
    assert bad_timezone.status_code == 422
    assert bad_timezone.json()["code"] == "SCHEDULE_TIMEZONE_INVALID"


@pytest.mark.parametrize(
    ("task_type", "payload", "job_type"),
    [
        ("retention_sync", {"account_ids": [], "limit": 10}, "account.retention_sync"),
        ("forwarding", {"account_ids": [], "limit": 10}, "account.forwarding_scan"),
    ],
)
async def test_scheduler_dispatches_all_automation_job_types(
    api_client: httpx.AsyncClient,
    task_type: str,
    payload: dict[str, object],
    job_type: str,
) -> None:
    created = await api_client.post(
        "/api/v1/schedules",
        json={
            "name": f"schedule-{task_type}",
            "task_type": task_type,
            "cron_expression": "* * * * *",
            "timezone": "UTC",
            "payload": payload,
        },
    )
    assert created.status_code == 201
    schedule_id = uuid.UUID(created.json()["id"])
    async with get_session_factory()() as session:
        schedule = await session.get(Schedule, schedule_id)
        assert schedule is not None
        schedule.next_run_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()
    async with get_session_factory()() as session:
        assert await run_due_schedules(session) == 1
    async with get_session_factory()() as session:
        schedule = await session.get(Schedule, schedule_id)
        assert schedule is not None and schedule.last_job_id is not None
        job = await session.get(Job, schedule.last_job_id)
        assert job is not None
        assert job.job_type == job_type
        assert job.status == "completed"


def test_next_schedule_run_is_timezone_aware() -> None:
    next_run = next_schedule_run(
        "0 9 * * *",
        "Asia/Shanghai",
        after=datetime(2026, 8, 28, 0, 30, tzinfo=UTC),
    )
    assert next_run == datetime(2026, 8, 28, 1, 0, tzinfo=UTC)
    with pytest.raises(ApiProblem):
        next_schedule_run("broken", "Asia/Shanghai")


async def test_provider_token_refresh_returns_rotated_tokens() -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "short-lived",
                "refresh_token": "rotated",
                "expires_in": 3600,
            },
        )

    account = ProviderAccount(
        id=uuid.uuid4(),
        email="provider@example.com",
        account_type="outlook",
        provider="outlook",
        authorization_type="graph",
        provider_metadata={"client_id": "client-id"},
    )
    secrets = DecryptedAccountSecrets(refresh_token="original")
    graph = GraphProvider(client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    imap = ImapProvider(
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport)),
    )
    graph_result = await graph.refresh_authorization(account, secrets)
    imap_result = await imap.refresh_authorization(account, secrets)
    assert graph_result.success is True
    assert graph_result.rotated_refresh_token == "rotated"
    assert imap_result.success is True
    assert imap_result.rotated_refresh_token == "rotated"
