from __future__ import annotations

import uuid

import httpx
import pytest

from smart_email_manager.config import get_settings
from smart_email_manager.db.models import Account, ProxyProfile
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.providers.base import ProviderAccount, ProviderOperationError
from smart_email_manager.providers.imap import ImapCredentials, ImapProvider
from smart_email_manager.providers.proxy_probe import ProxyProbeResult
from smart_email_manager.providers.registry import proxy_variants
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services import proxies
from smart_email_manager.services.proxies import resolve_account_proxy


class FallbackHealthyProber:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def probe(self, proxy_url: str) -> ProxyProbeResult:
        self.urls.append(proxy_url)
        if len(self.urls) == 1:
            return ProxyProbeResult(False, "PROXY_CONNECT_FAILED", 12, "primary down")
        return ProxyProbeResult(True, "PROXY_OK", 20)


async def test_encrypted_proxy_inheritance_override_and_placeholder(
    api_client: httpx.AsyncClient,
) -> None:
    parent = await api_client.post("/api/v1/groups", json={"name": "代理父组"})
    child = await api_client.post(
        "/api/v1/groups",
        json={"name": "代理子组", "parent_id": parent.json()["id"]},
    )
    account = await api_client.post(
        "/api/v1/accounts",
        json={"email": "A.B+proxy@example.com", "group_id": child.json()["id"]},
    )
    account_id = uuid.UUID(account.json()["id"])

    profile = await api_client.post(
        "/api/v1/proxies",
        json={
            "name": "group resin",
            "primary_url": "socks5h://platform.{mail}:secret@127.0.0.1:1080",
            "fallback_url_1": "direct",
            "fallback_url_2": "socks5://backup:pass@127.0.0.2:1081",
        },
    )
    assert profile.status_code == 201
    assert "secret" not in profile.text
    assert "pass" not in profile.text
    profile_id = uuid.UUID(profile.json()["id"])
    assigned = await api_client.put(
        f"/api/v1/proxies/groups/{parent.json()['id']}",
        json={"proxy_profile_id": str(profile_id)},
    )
    assert assigned.status_code == 204

    resolved_api = await api_client.get(f"/api/v1/proxies/accounts/{account_id}/resolved")
    assert resolved_api.status_code == 200
    assert resolved_api.json()["source"] == "group"
    assert resolved_api.json()["endpoint_hints"] == [
        "socks5h://127.0.0.1:1080",
        "direct",
        "socks5://127.0.0.2:1081",
    ]

    async with get_session_factory()() as session:
        row = await session.get(ProxyProfile, profile_id)
        assert row is not None
        assert b"secret" not in row.primary_url_ciphertext
        resolved = await resolve_account_proxy(
            session,
            account_id,
            AccountSecretCipher.from_settings(get_settings()),
        )
        assert "platform.abproxy:secret" in resolved.urls[0]
        assert resolved.urls[1] == "direct"

    override = await api_client.post(
        "/api/v1/proxies",
        json={"name": "account direct", "primary_url": "http://127.0.0.3:8080"},
    )
    override_id = override.json()["id"]
    assert (
        await api_client.put(
            f"/api/v1/proxies/accounts/{account_id}",
            json={"proxy_profile_id": override_id},
        )
    ).status_code == 204
    assert (await api_client.get(f"/api/v1/proxies/accounts/{account_id}/resolved")).json()[
        "source"
    ] == "account"


def test_proxy_variants_preserve_order_and_direct_fallback() -> None:
    account = ProviderAccount(
        id=uuid.uuid4(),
        email="proxy@example.com",
        account_type="outlook",
        provider="outlook",
        authorization_type="graph",
        provider_metadata={},
        proxy_urls=("http://one:8080", "direct", "socks5://two:1080"),
    )
    assert [item.proxy_urls for item in proxy_variants(account)] == [
        ("http://one:8080",),
        (),
        ("socks5://two:1080",),
    ]


def test_imap_rejects_non_socks_raw_proxy() -> None:
    with pytest.raises(ProviderOperationError) as error:
        ImapProvider._open_client(
            ImapCredentials(
                host="imap.example.com",
                port=993,
                email="imap@example.com",
                access_token="access-token",
                proxy_url="http://127.0.0.1:8080",
            )
        )
    assert error.value.code == "IMAP_PROXY_UNSUPPORTED"


async def test_proxy_probe_uses_fallback_and_returns_only_sanitized_hints(
    api_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = await api_client.post(
        "/api/v1/accounts",
        json={"email": "proxy-probe@example.com"},
    )
    account_id = uuid.UUID(account.json()["id"])
    profile = await api_client.post(
        "/api/v1/proxies",
        json={
            "name": "probe profile",
            "primary_url": "socks5h://primary-user:primary-secret@127.0.0.1:1080",
            "fallback_url_1": "http://fallback-user:fallback-secret@127.0.0.2:8080",
        },
    )
    profile_id = uuid.UUID(profile.json()["id"])
    await api_client.put(
        f"/api/v1/proxies/accounts/{account_id}",
        json={"proxy_profile_id": str(profile_id)},
    )
    prober = FallbackHealthyProber()
    monkeypatch.setattr(proxies, "PROXY_PROBER", prober)
    response = await api_client.post(f"/api/v1/proxies/{profile_id}/probe")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert payload["reason_code"] == "PROXY_FALLBACK_OK"
    assert [item["endpoint_hint"] for item in payload["attempts"]] == [
        "socks5h://127.0.0.1:1080",
        "http://127.0.0.2:8080",
    ]
    assert "secret" not in response.text
    assert "user" not in response.text
    assert "primary-secret" in prober.urls[0]
    async with get_session_factory()() as session:
        profile_row = await session.get(ProxyProfile, profile_id)
        account_row = await session.get(Account, account_id)
        assert profile_row is not None and account_row is not None
        assert profile_row.health_status == "healthy"
        assert profile_row.last_tested_at is not None
        assert account_row.proxy_health_status == "healthy"
