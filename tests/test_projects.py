from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from smart_email_manager.db.models import ProjectAccount
from smart_email_manager.db.session import get_session_factory


async def test_project_work_leases_are_atomic_expirable_and_token_guarded(
    api_client: httpx.AsyncClient,
) -> None:
    account_ids: list[str] = []
    for index in range(2):
        response = await api_client.post(
            "/api/v1/accounts",
            json={"email": f"project-{index}@example.com", "provider": "outlook"},
        )
        account_ids.append(response.json()["id"])
    project_response = await api_client.post(
        "/api/v1/projects",
        json={
            "name": "Parallel mailbox work",
            "description": "Lease accounts without duplicate work",
            "default_lease_seconds": 60,
            "account_ids": account_ids,
        },
    )
    assert project_response.status_code == 201
    project_id = uuid.UUID(project_response.json()["id"])

    first_claim, second_claim = await asyncio.gather(
        api_client.post(
            f"/api/v1/projects/{project_id}/claims",
            json={"owner": "worker-a"},
        ),
        api_client.post(
            f"/api/v1/projects/{project_id}/claims",
            json={"owner": "worker-b"},
        ),
    )
    assert first_claim.status_code == 200
    assert second_claim.status_code == 200
    first_payload = first_claim.json()
    second_payload = second_claim.json()
    assert first_payload["account_id"] != second_payload["account_id"]
    assert first_payload["claim_token"].startswith("sem_claim_")
    no_more = await api_client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"owner": "worker-c"},
    )
    assert no_more.status_code == 409
    assert no_more.json()["code"] == "PROJECT_WORK_UNAVAILABLE"

    wrong = await api_client.post(
        f"/api/v1/projects/leases/{first_payload['project_account_id']}/heartbeat",
        json={"claim_token": "wrong-token"},
    )
    heartbeat = await api_client.post(
        f"/api/v1/projects/leases/{first_payload['project_account_id']}/heartbeat",
        json={"claim_token": first_payload["claim_token"], "lease_seconds": 120},
    )
    assert wrong.status_code == 409
    assert heartbeat.status_code == 200

    completed = await api_client.post(
        f"/api/v1/projects/leases/{first_payload['project_account_id']}/complete",
        json={
            "claim_token": first_payload["claim_token"],
            "result": {"processed": True},
        },
    )
    assert completed.json()["status"] == "done"
    assert "claim_token" not in completed.json()

    second_id = uuid.UUID(second_payload["project_account_id"])
    async with get_session_factory()() as session:
        leased = await session.get(ProjectAccount, second_id)
        assert leased is not None
        assert leased.lease_token_hash is not None
        assert second_payload["claim_token"].encode() not in leased.lease_token_hash
        leased.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    reclaimed = await api_client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"owner": "worker-c"},
    )
    assert reclaimed.status_code == 200
    assert reclaimed.json()["project_account_id"] == str(second_id)
    assert reclaimed.json()["attempt_count"] == 2
    failed = await api_client.post(
        f"/api/v1/projects/leases/{second_id}/fail",
        json={
            "claim_token": reclaimed.json()["claim_token"],
            "error_summary": "provider failed",
        },
    )
    assert failed.json()["status"] == "failed"

    projects = await api_client.get("/api/v1/projects")
    project = projects.json()[0]
    assert project["done_count"] == 1
    assert project["failed_count"] == 1
    assert project["leased_count"] == 0
    events = await api_client.get(f"/api/v1/projects/{project_id}/events")
    event_types = {item["event_type"] for item in events.json()}
    assert {
        "project.created",
        "account.leased",
        "account.heartbeat",
        "account.done",
        "account.failed",
    } <= event_types

    paused = await api_client.put(
        f"/api/v1/projects/{project_id}/status",
        json={"status": "paused"},
    )
    assert paused.json()["status"] == "paused"


async def test_project_accounts_support_controlled_reset_remove_and_restore(
    api_client: httpx.AsyncClient,
) -> None:
    account = await api_client.post(
        "/api/v1/accounts",
        json={"email": "project-actions@example.com", "provider": "outlook"},
    )
    project = await api_client.post(
        "/api/v1/projects",
        json={"name": "Controlled project actions", "account_ids": [account.json()["id"]]},
    )
    project_id = project.json()["id"]
    claim = await api_client.post(
        f"/api/v1/projects/{project_id}/claims",
        json={"owner": "worker-actions"},
    )
    project_account_id = claim.json()["project_account_id"]
    failed = await api_client.post(
        f"/api/v1/projects/leases/{project_account_id}/fail",
        json={"claim_token": claim.json()["claim_token"], "error_summary": "acceptance"},
    )
    assert failed.json()["status"] == "failed"

    reset = await api_client.post(
        f"/api/v1/projects/{project_id}/account-actions",
        json={"action": "reset_failed", "project_account_ids": [project_account_id]},
    )
    assert reset.status_code == 200
    assert reset.json()["updated_count"] == 1
    rows = await api_client.get(f"/api/v1/projects/{project_id}/accounts")
    assert rows.json()[0]["status"] == "to_claim"

    removed = await api_client.post(
        f"/api/v1/projects/{project_id}/account-actions",
        json={"action": "remove", "project_account_ids": [project_account_id]},
    )
    assert removed.json()["updated_count"] == 1
    assert (await api_client.get(f"/api/v1/projects/{project_id}/accounts")).json()[0]["status"] == "removed"

    restored = await api_client.post(
        f"/api/v1/projects/{project_id}/account-actions",
        json={"action": "restore", "project_account_ids": [project_account_id]},
    )
    assert restored.json()["updated_count"] == 1
    assert (await api_client.get(f"/api/v1/projects/{project_id}/accounts")).json()[0]["status"] == "to_claim"

    events = await api_client.get(f"/api/v1/projects/{project_id}/events")
    assert {
        "accounts.reset_failed",
        "accounts.remove",
        "accounts.restore",
    } <= {event["event_type"] for event in events.json()}
