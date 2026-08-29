from __future__ import annotations

import uuid

import httpx
from sqlalchemy import func, select

from smart_email_manager.config import get_settings
from smart_email_manager.db.models import Account, AccountSecret, ImportBatchItem
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.security.encryption import AccountSecretCipher
from tests.test_api_vertical_slice import create_account

CLIENT_ID = "11111111-2222-3333-4444-555555555555"


async def test_import_preflight_commit_and_guarded_rollback(api_client: httpx.AsyncClient) -> None:
    existing_id = await create_account("existing@example.com")
    content = "\n".join(
        [
            f"new@example.com----mail-password----{CLIENT_ID}----refresh-value",
            "not-an-email----password----client----token",
            f"new@example.com----duplicate----{CLIENT_ID}----duplicate-token",
            f"existing@example.com----existing----{CLIENT_ID}----existing-token",
        ]
    )
    preflight = await api_client.post(
        "/api/v1/import-batches",
        headers={"Idempotency-Key": "import-test-1"},
        json={"content": content, "account_type": "outlook", "provider": "outlook"},
    )
    assert preflight.status_code == 201
    batch = preflight.json()
    assert batch["status"] == "validated"
    assert batch["total_count"] == 4
    assert batch["valid_count"] == 1
    assert batch["invalid_count"] == 1
    assert batch["conflict_count"] == 2
    assert "mail-password" not in preflight.text
    batch_id = batch["id"]

    async with get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(Account)) == 1
        staged = await session.scalar(
            select(ImportBatchItem).where(
                ImportBatchItem.batch_id == uuid.UUID(batch_id),
                ImportBatchItem.status == "valid",
            )
        )
        assert staged is not None
        assert staged.password_ciphertext
        assert b"mail-password" not in staged.password_ciphertext

    same = await api_client.post(
        "/api/v1/import-batches",
        headers={"Idempotency-Key": "import-test-1"},
        json={"content": content, "account_type": "outlook", "provider": "outlook"},
    )
    assert same.json()["id"] == batch_id

    committed = await api_client.post(f"/api/v1/import-batches/{batch_id}/commit")
    assert committed.status_code == 200
    assert committed.json()["status"] == "partial"
    assert committed.json()["created_count"] == 1

    async with get_session_factory()() as session:
        new_account = await session.scalar(
            select(Account).where(Account.email_normalized == "new@example.com")
        )
        assert new_account is not None
        assert new_account.provider_metadata["client_id"] == CLIENT_ID
        secret = await session.get(AccountSecret, new_account.id)
        assert secret is not None
        cipher = AccountSecretCipher.from_settings(get_settings())
        assert (
            cipher.decrypt(
                new_account.id,
                "refresh_token",
                secret.refresh_token_ciphertext or b"",
                secret.key_version,
            )
            == "refresh-value"
        )

    rolled_back = await api_client.post(f"/api/v1/import-batches/{batch_id}/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"

    async with get_session_factory()() as session:
        assert await session.get(Account, existing_id) is not None
        assert (
            await session.scalar(
                select(func.count()).select_from(Account).where(Account.email_normalized == "new@example.com")
            )
            == 0
        )
