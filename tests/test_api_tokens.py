from __future__ import annotations

import uuid

import httpx


async def test_persistent_token_scope_and_revocation(api_client: httpx.AsyncClient) -> None:
    admin_response = await api_client.post(
        "/api/v1/auth/tokens",
        json={"name": "test admin", "scopes": ["*"], "expires_in_days": 1},
    )
    assert admin_response.status_code == 201
    admin_secret = admin_response.json()["secret"]
    assert admin_secret.startswith("sem_")
    assert "token_hash" not in admin_response.text
    admin_headers = {"Authorization": f"Bearer {admin_secret}"}

    anonymous = await api_client.get("/api/v1/accounts")
    assert anonymous.status_code == 401

    limited_response = await api_client.post(
        "/api/v1/auth/tokens",
        headers=admin_headers,
        json={
            "name": "read-only automation",
            "scopes": ["accounts:read", "fleet:read"],
            "expires_in_days": 30,
        },
    )
    assert limited_response.status_code == 201
    limited_secret = limited_response.json()["secret"]
    limited_id = uuid.UUID(limited_response.json()["token"]["id"])
    limited_headers = {"Authorization": f"Bearer {limited_secret}"}

    assert (await api_client.get("/api/v1/accounts", headers=limited_headers)).status_code == 200
    denied = await api_client.post(
        "/api/v1/accounts",
        headers=limited_headers,
        json={"email": "denied@example.com"},
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "INSUFFICIENT_SCOPE"

    listed = await api_client.get("/api/v1/auth/tokens", headers=admin_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert all("token_hash" not in item for item in listed.json())

    revoked = await api_client.post(
        f"/api/v1/auth/tokens/{limited_id}/revoke",
        headers=admin_headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert (await api_client.get("/api/v1/accounts", headers=limited_headers)).status_code == 401
