from __future__ import annotations

import uuid

import httpx
from sqlalchemy import select

from smart_email_manager.db.models import Account, AccountForwarding, AccountTag
from smart_email_manager.db.session import get_session_factory


async def test_account_update_bulk_archive_and_guarded_purge(
    api_client: httpx.AsyncClient,
) -> None:
    first = await api_client.post(
        "/api/v1/accounts",
        json={"email": "bulk-one@example.com", "provider": "outlook"},
    )
    second = await api_client.post(
        "/api/v1/accounts",
        json={"email": "bulk-two@example.com", "provider": "outlook"},
    )
    first_payload = first.json()
    first_id = uuid.UUID(first_payload["id"])
    second_id = uuid.UUID(second.json()["id"])
    group = await api_client.post("/api/v1/groups", json={"name": "Bulk target"})
    tag = await api_client.post(
        "/api/v1/tags",
        json={"name": "bulk-tag", "color": "#2563eb"},
    )
    group_id = uuid.UUID(group.json()["id"])
    tag_id = uuid.UUID(tag.json()["id"])

    updated = await api_client.patch(
        f"/api/v1/accounts/{first_id}",
        json={
            "row_version": first_payload["row_version"],
            "remark": "managed account",
            "provider_metadata": {"client_id": "client-id"},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["remark"] == "managed account"
    assert updated.json()["row_version"] == first_payload["row_version"] + 1
    stale = await api_client.patch(
        f"/api/v1/accounts/{first_id}",
        json={"row_version": first_payload["row_version"], "remark": "stale write"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "ACCOUNT_VERSION_CONFLICT"

    missing_id = uuid.uuid4()
    bulk = await api_client.post(
        "/api/v1/accounts/bulk/mutations",
        json={
            "account_ids": [str(first_id), str(second_id), str(missing_id)],
            "lifecycle_status": "inactive",
            "move_group": True,
            "group_id": str(group_id),
            "add_tag_ids": [str(tag_id)],
            "forwarding_enabled": True,
        },
    )
    assert bulk.status_code == 200
    assert bulk.json()["matched_count"] == 2
    assert bulk.json()["not_found_ids"] == [str(missing_id)]
    async with get_session_factory()() as session:
        accounts = list(
            (await session.scalars(select(Account).where(Account.id.in_([first_id, second_id])))).all()
        )
        forwarding = list(
            (
                await session.scalars(
                    select(AccountForwarding).where(AccountForwarding.account_id.in_([first_id, second_id]))
                )
            ).all()
        )
        tag_links = list(
            (
                await session.scalars(
                    select(AccountTag).where(
                        AccountTag.account_id.in_([first_id, second_id]),
                        AccountTag.tag_id == tag_id,
                    )
                )
            ).all()
        )
        assert all(item.lifecycle_status == "inactive" for item in accounts)
        assert all(item.group_id == group_id for item in accounts)
        assert len(forwarding) == 2
        assert all(item.enabled for item in forwarding)
        assert len(tag_links) == 2

    current = await api_client.get(f"/api/v1/accounts/{first_id}")
    archived = await api_client.post(
        f"/api/v1/accounts/{first_id}/archive",
        json={"row_version": current.json()["row_version"]},
    )
    assert archived.status_code == 200
    assert archived.json()["lifecycle_status"] == "archived"
    wrong_purge = await api_client.delete(
        f"/api/v1/accounts/{first_id}",
        params={"confirm_email": "wrong@example.com"},
    )
    assert wrong_purge.status_code == 409
    purged = await api_client.delete(
        f"/api/v1/accounts/{first_id}",
        params={"confirm_email": "bulk-one@example.com"},
    )
    assert purged.status_code == 204
    missing = await api_client.get(f"/api/v1/accounts/{first_id}")
    assert missing.status_code == 404
    audit = await api_client.get(
        "/api/v1/audit-logs",
        params={"resource_type": "account", "resource_id": str(first_id)},
    )
    assert {item["action"] for item in audit.json()} == {
        "account.archive",
        "account.purge",
    }
