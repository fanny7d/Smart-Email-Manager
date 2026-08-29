from __future__ import annotations

import httpx

from smart_email_manager.api.schemas.secrets import AccountSecretsWrite
from smart_email_manager.config import get_settings
from smart_email_manager.db.models import AccountSecret
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.security.encryption import AccountSecretCipher
from tests.test_api_vertical_slice import create_account


async def test_account_secrets_are_encrypted_and_never_returned(api_client: httpx.AsyncClient) -> None:
    account_id = await create_account("secret-test@example.com")
    response = await api_client.put(
        f"/api/v1/accounts/{account_id}/secrets",
        json={
            "password": "mail-password",
            "refresh_token": "refresh-token-value",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "account_id": str(account_id),
        "has_password": True,
        "has_refresh_token": True,
        "key_version": 1,
    }
    assert "mail-password" not in response.text
    assert "refresh-token-value" not in response.text

    async with get_session_factory()() as session:
        row = await session.get(AccountSecret, account_id)
        assert row is not None
        assert b"mail-password" not in (row.password_ciphertext or b"")
        cipher = AccountSecretCipher.from_settings(get_settings())
        assert cipher.decrypt(account_id, "password", row.password_ciphertext or b"", row.key_version) == (
            "mail-password"
        )

    status = await api_client.get(f"/api/v1/accounts/{account_id}/secrets/status")
    assert status.status_code == 200
    assert "ciphertext" not in status.text


def test_secret_write_schema_masks_values() -> None:
    payload = AccountSecretsWrite(password="hidden")
    assert "hidden" not in repr(payload)
