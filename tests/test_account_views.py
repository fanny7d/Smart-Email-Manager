from __future__ import annotations

import uuid

import httpx

from smart_email_manager.db.models import Account
from smart_email_manager.db.session import get_session_factory


async def _create_account(api_client: httpx.AsyncClient, email: str) -> uuid.UUID:
    response = await api_client.post(
        "/api/v1/accounts",
        json={"email": email, "provider": "outlook"},
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


async def test_builtin_and_saved_account_views(api_client: httpx.AsyncClient) -> None:
    healthy_id = await _create_account(api_client, "healthy-view@example.com")
    failed_id = await _create_account(api_client, "failed-view@example.com")
    async with get_session_factory()() as session:
        healthy = await session.get(Account, healthy_id)
        failed = await session.get(Account, failed_id)
        assert healthy is not None and failed is not None
        healthy.authorization_status = "valid"
        healthy.token_status = "success"
        healthy.mail_health_status = "healthy"
        failed.authorization_status = "reauthorization_required"
        failed.token_status = "failed"
        failed.mail_health_status = "failed"
        failed.consecutive_failures = 3
        await session.commit()

    views = await api_client.get("/api/v1/fleet/views")
    assert views.status_code == 200
    builtin_keys = {item["key"] for item in views.json()["builtin"]}
    assert {
        "pending_verification",
        "healthy",
        "reauthorization",
        "token_failed",
        "proxy_failed",
        "consecutive_failures",
        "stale_mail",
        "inactive",
        "ungrouped",
        "untagged",
    } <= builtin_keys

    healthy_page = await api_client.get("/api/v1/accounts", params={"view": "healthy"})
    assert healthy_page.status_code == 200
    assert [item["id"] for item in healthy_page.json()["items"]] == [str(healthy_id)]

    created = await api_client.post(
        "/api/v1/fleet/views",
        json={
            "name": "需要处理",
            "filters": {
                "mail_health_statuses": ["failed"],
                "min_consecutive_failures": 2,
            },
            "sort_order": 20,
        },
    )
    assert created.status_code == 201
    saved_view_id = created.json()["id"]
    saved_page = await api_client.get(
        "/api/v1/accounts",
        params={"saved_view_id": saved_view_id},
    )
    assert saved_page.status_code == 200
    assert [item["id"] for item in saved_page.json()["items"]] == [str(failed_id)]

    updated = await api_client.put(
        f"/api/v1/fleet/views/{saved_view_id}",
        json={
            "name": "Token 失败",
            "filters": {"token_statuses": ["failed", "stale"]},
            "sort_order": 1,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Token 失败"
    assert updated.json()["sort_order"] == 1

    ambiguous = await api_client.get(
        "/api/v1/accounts",
        params={"view": "healthy", "saved_view_id": saved_view_id},
    )
    assert ambiguous.status_code == 400
    assert ambiguous.json()["code"] == "ACCOUNT_VIEW_AMBIGUOUS"

    deleted = await api_client.delete(f"/api/v1/fleet/views/{saved_view_id}")
    assert deleted.status_code == 204
    missing = await api_client.get(
        "/api/v1/accounts",
        params={"saved_view_id": saved_view_id},
    )
    assert missing.status_code == 404
