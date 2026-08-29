from __future__ import annotations

import os
import uuid

import httpx
import pytest

from smart_email_manager.config import get_settings
from smart_email_manager.db.models import (
    AccountSecret,
    ForwardingDestination,
    ProxyProfile,
)
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.security.encryption import AccountSecretCipher


async def test_master_key_rotation_dry_run_then_atomic_commit(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await api_client.post(
        "/api/v1/accounts",
        json={"email": "rotate@example.com", "provider": "outlook"},
    )
    account_id = uuid.UUID(account.json()["id"])
    await api_client.put(
        f"/api/v1/accounts/{account_id}/secrets",
        json={"password": "rotate-password", "refresh_token": "rotate-token"},
    )
    proxy = await api_client.post(
        "/api/v1/proxies",
        json={
            "name": "rotate-proxy",
            "primary_url": "socks5h://user:password@127.0.0.1:1080",
            "enabled": True,
        },
    )
    forwarding = await api_client.post(
        "/api/v1/forwarding/destinations",
        json={
            "name": "rotate-forwarding",
            "channel": "smtp",
            "config": {"host": "smtp.example.test", "recipient": "target@example.test"},
            "secret": "rotate-smtp-password",
        },
    )
    assert all(response.status_code == 201 for response in (proxy, forwarding))
    old_key = os.environ["SEM_MASTER_KEY"]
    monkeypatch.setenv("SEM_MASTER_KEY_VERSION", "2")
    get_settings.cache_clear()

    dry_run = await api_client.post(
        "/api/v1/security/master-key-rotations",
        json={"old_master_key": old_key, "old_key_version": 1, "commit": False},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["committed"] is False
    assert dry_run.json()["account_secrets"] == 1
    assert dry_run.json()["proxy_profiles"] == 1
    assert dry_run.json()["forwarding_destinations"] == 1
    async with get_session_factory()() as session:
        secret = await session.get(AccountSecret, account_id)
        assert secret is not None
        assert secret.key_version == 1

    committed = await api_client.post(
        "/api/v1/security/master-key-rotations",
        json={"old_master_key": old_key, "old_key_version": 1, "commit": True},
    )
    assert committed.status_code == 200
    assert committed.json()["committed"] is True
    cipher = AccountSecretCipher.from_settings(get_settings())
    async with get_session_factory()() as session:
        secret = await session.get(AccountSecret, account_id)
        proxy_row = await session.get(ProxyProfile, uuid.UUID(proxy.json()["id"]))
        forwarding_row = await session.get(ForwardingDestination, uuid.UUID(forwarding.json()["id"]))
        assert all(
            row is not None and row.key_version == 2
            for row in (secret, proxy_row, forwarding_row)
        )
        assert secret is not None and secret.password_ciphertext is not None
        assert (
            cipher.decrypt(
                account_id,
                "password",
                secret.password_ciphertext,
                secret.key_version,
            )
            == "rotate-password"
        )
        assert proxy_row is not None
        assert (
            cipher.decrypt_context(
                f"proxy:{proxy_row.id}",
                "primary_url",
                proxy_row.primary_url_ciphertext,
                proxy_row.key_version,
            )
            == "socks5h://user:password@127.0.0.1:1080"
        )
