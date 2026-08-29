from __future__ import annotations

import httpx


async def _create_account(api_client: httpx.AsyncClient, email: str) -> dict[str, object]:
    response = await api_client.post(
        "/api/v1/accounts",
        json={"email": email, "provider": "outlook"},
    )
    assert response.status_code == 201
    return response.json()


async def test_bulk_preview_freezes_filter_scope_and_is_single_use(
    api_client: httpx.AsyncClient,
) -> None:
    first = await _create_account(api_client, "bulk-one@example.com")
    second = await _create_account(api_client, "bulk-two@example.com")
    preview_response = await api_client.post(
        "/api/v1/accounts/bulk/previews",
        json={
            "selection": {"scope": "filter", "lifecycle_status": "active"},
            "changes": {"lifecycle_status": "inactive"},
        },
    )
    assert preview_response.status_code == 201
    preview = preview_response.json()
    assert preview["scope"] == "filter"
    assert preview["matched_count"] == 2
    assert preview["eligible_count"] == 2
    assert preview["skipped_count"] == 0
    assert preview["dangerous_count"] == 0

    third = await _create_account(api_client, "bulk-three-after-preview@example.com")
    execute = await api_client.post(
        "/api/v1/accounts/bulk/executions",
        json={"preview_token": preview["preview_token"]},
    )
    assert execute.status_code == 200
    assert execute.json()["matched_count"] == 2
    assert execute.json()["updated_count"] == 2

    assert (await api_client.get(f"/api/v1/accounts/{first['id']}")).json()["lifecycle_status"] == "inactive"
    assert (await api_client.get(f"/api/v1/accounts/{second['id']}")).json()["lifecycle_status"] == "inactive"
    assert (await api_client.get(f"/api/v1/accounts/{third['id']}")).json()["lifecycle_status"] == "active"

    reused = await api_client.post(
        "/api/v1/accounts/bulk/executions",
        json={"preview_token": preview["preview_token"]},
    )
    assert reused.status_code == 409
    assert reused.json()["code"] == "BULK_PREVIEW_ALREADY_USED"


async def test_bulk_preview_reports_noop_and_dangerous_counts(
    api_client: httpx.AsyncClient,
) -> None:
    existing = await _create_account(api_client, "bulk-noop@example.com")
    noop = await api_client.post(
        "/api/v1/accounts/bulk/previews",
        json={
            "selection": {"scope": "ids", "account_ids": [existing["id"]]},
            "changes": {"lifecycle_status": "active"},
        },
    )
    assert noop.status_code == 201
    assert noop.json()["eligible_count"] == 0
    assert noop.json()["skipped_count"] == 1

    dangerous = await api_client.post(
        "/api/v1/accounts/bulk/previews",
        json={
            "selection": {"scope": "ids", "account_ids": [existing["id"]]},
            "changes": {"lifecycle_status": "archived"},
        },
    )
    assert dangerous.status_code == 201
    assert dangerous.json()["eligible_count"] == 1
    assert dangerous.json()["dangerous_count"] == 1
