from __future__ import annotations

import uuid

import httpx


async def _create_group(
    api_client: httpx.AsyncClient,
    name: str,
    parent_id: str | None = None,
) -> dict[str, object]:
    response = await api_client.post(
        "/api/v1/groups",
        json={"name": name, "parent_id": parent_id, "color": "#334155"},
    )
    assert response.status_code == 201
    return response.json()


async def test_three_level_groups_counts_and_cascade_delete(api_client: httpx.AsyncClient) -> None:
    initial = await api_client.get("/api/v1/groups")
    assert initial.status_code == 200
    assert {item["system_key"] for item in initial.json()} == {"default"}

    parent = await _create_group(api_client, "客户 A")
    child = await _create_group(api_client, "项目 1", str(parent["id"]))
    grandchild = await _create_group(api_client, "用途 X", str(child["id"]))
    too_deep = await api_client.post(
        "/api/v1/groups",
        json={"name": "非法四级", "parent_id": grandchild["id"]},
    )
    assert too_deep.status_code == 409
    assert too_deep.json()["code"] == "GROUP_DEPTH_EXCEEDED"

    cycle = await api_client.put(
        f"/api/v1/groups/{parent['id']}",
        json={"parent_id": grandchild["id"]},
    )
    assert cycle.status_code == 409
    assert cycle.json()["code"] == "GROUP_CYCLE"

    account = await api_client.post(
        "/api/v1/accounts",
        json={"email": "grouped@example.com", "group_id": grandchild["id"]},
    )
    assert account.status_code == 201
    account_id = account.json()["id"]

    groups = (await api_client.get("/api/v1/groups")).json()
    parent_row = next(item for item in groups if item["id"] == parent["id"])
    grandchild_row = next(item for item in groups if item["id"] == grandchild["id"])
    assert parent_row["descendant_account_count"] == 1
    assert grandchild_row["direct_account_count"] == 1

    deleted = await api_client.delete(f"/api/v1/groups/{parent['id']}")
    assert deleted.status_code == 204
    accounts = (await api_client.get("/api/v1/accounts")).json()["items"]
    moved = next(item for item in accounts if item["id"] == account_id)
    default_group = next(
        item for item in (await api_client.get("/api/v1/groups")).json() if item["system_key"] == "default"
    )
    assert moved["group_id"] == default_group["id"]

    protected = await api_client.delete(f"/api/v1/groups/{default_group['id']}")
    assert protected.status_code == 409
    assert protected.json()["code"] == "SYSTEM_GROUP_IMMUTABLE"


async def test_tags_and_aliases_preserve_uniqueness(api_client: httpx.AsyncClient) -> None:
    account = await api_client.post("/api/v1/accounts", json={"email": "primary@example.com"})
    other = await api_client.post("/api/v1/accounts", json={"email": "other@example.com"})
    account_id = uuid.UUID(account.json()["id"])

    tag = await api_client.post("/api/v1/tags", json={"name": "批次 A", "color": "#2563eb"})
    assert tag.status_code == 201
    tag_id = tag.json()["id"]
    assigned = await api_client.put(
        f"/api/v1/accounts/{account_id}/tags",
        json={"action": "add", "tag_ids": [tag_id]},
    )
    assert [item["name"] for item in assigned.json()] == ["批次 A"]

    aliases = await api_client.put(
        f"/api/v1/accounts/{account_id}/aliases",
        json={"aliases": ["alias@example.com"]},
    )
    assert aliases.status_code == 200
    assert aliases.json()[0]["email"] == "alias@example.com"

    conflict = await api_client.put(
        f"/api/v1/accounts/{account_id}/aliases",
        json={"aliases": [other.json()["email"]]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "ALIAS_CONFLICT"
