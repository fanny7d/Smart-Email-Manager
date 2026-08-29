from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.proxies import (
    ProxyProbeAttemptRead,
    ProxyProbeRead,
    ProxyProfileRead,
    ProxyProfileWrite,
    ResolvedProxyRead,
)
from smart_email_manager.db.models import Account, Group, ProxyProfile
from smart_email_manager.providers.proxy_probe import ProxyProber
from smart_email_manager.security.encryption import AccountSecretCipher

ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
PROXY_PROBER = ProxyProber()


@dataclass(frozen=True)
class ResolvedProxy:
    account_id: uuid.UUID
    source: Literal["account", "group", "none"]
    source_group_id: uuid.UUID | None
    profile_id: uuid.UUID | None
    profile_name: str | None
    urls: tuple[str, ...]


def validate_proxy_url(value: str, *, allow_direct: bool) -> str:
    normalized = value.strip()
    if allow_direct and normalized.lower() == "direct":
        return "direct"
    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in ALLOWED_PROXY_SCHEMES or not parsed.hostname:
        raise ApiProblem(
            status=422,
            code="PROXY_URL_INVALID",
            title="Proxy URL is invalid",
            detail="Use http(s)://, socks5:// or socks5h:// with a hostname.",
        )
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ApiProblem(
            status=422,
            code="PROXY_URL_INVALID",
            title="Proxy URL port is invalid",
            detail="Proxy ports must be between 1 and 65535.",
        )
    return normalized


def proxy_hint(value: str) -> str:
    if value == "direct":
        return value
    parsed = urlparse(value)
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname or ''}{port}"


def _context(profile_id: uuid.UUID) -> str:
    return f"proxy:{profile_id}"


def _encrypt_url(
    cipher: AccountSecretCipher,
    profile_id: uuid.UUID,
    field_name: str,
    value: str | None,
) -> bytes | None:
    if value is None or not value.strip():
        return None
    return cipher.encrypt_context(
        _context(profile_id),
        field_name,
        validate_proxy_url(value, allow_direct=field_name != "primary_url"),
    ).ciphertext


def _decrypt_url(
    cipher: AccountSecretCipher,
    profile: ProxyProfile,
    field_name: str,
) -> str | None:
    ciphertext = getattr(profile, f"{field_name}_ciphertext")
    if not ciphertext:
        return None
    return cipher.decrypt_context(
        _context(profile.id),
        field_name,
        ciphertext,
        profile.key_version,
    )


async def write_proxy_profile(
    session: AsyncSession,
    *,
    payload: ProxyProfileWrite,
    cipher: AccountSecretCipher,
    profile_id: uuid.UUID | None = None,
) -> ProxyProfile:
    if profile_id:
        profile = await session.get(ProxyProfile, profile_id)
        if not profile:
            raise ApiProblem(
                status=404,
                code="PROXY_PROFILE_NOT_FOUND",
                title="Proxy profile not found",
                detail=f"No proxy profile exists with id {profile_id}.",
            )
        if profile.key_version != cipher.key_version:
            raise ApiProblem(
                status=409,
                code="PROXY_KEY_ROTATION_REQUIRED",
                title="Proxy profile uses another key version",
                detail="Rotate this proxy profile before updating it.",
            )
    else:
        profile = ProxyProfile(
            name=payload.name.strip(),
            primary_url_ciphertext=b"pending",
            key_version=cipher.key_version,
        )
        session.add(profile)
        await session.flush()

    profile.name = payload.name.strip()
    profile.enabled = payload.enabled
    profile.primary_url_ciphertext = (
        _encrypt_url(
            cipher,
            profile.id,
            "primary_url",
            payload.primary_url.get_secret_value(),
        )
        or b""
    )
    profile.fallback_url_1_ciphertext = _encrypt_url(
        cipher,
        profile.id,
        "fallback_url_1",
        payload.fallback_url_1.get_secret_value() if payload.fallback_url_1 else None,
    )
    profile.fallback_url_2_ciphertext = _encrypt_url(
        cipher,
        profile.id,
        "fallback_url_2",
        payload.fallback_url_2.get_secret_value() if payload.fallback_url_2 else None,
    )
    profile.key_version = cipher.key_version
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="PROXY_PROFILE_NAME_CONFLICT",
            title="Proxy profile name already exists",
            detail=f"A proxy profile already uses {payload.name.strip()}.",
        ) from exc
    await session.refresh(profile)
    return profile


def serialize_proxy_profile(
    profile: ProxyProfile,
    cipher: AccountSecretCipher,
) -> ProxyProfileRead:
    primary = _decrypt_url(cipher, profile, "primary_url") or ""
    fallback_1 = _decrypt_url(cipher, profile, "fallback_url_1")
    fallback_2 = _decrypt_url(cipher, profile, "fallback_url_2")
    return ProxyProfileRead(
        id=profile.id,
        name=profile.name,
        enabled=profile.enabled,
        primary_hint=proxy_hint(primary),
        fallback_hint_1=proxy_hint(fallback_1) if fallback_1 else None,
        fallback_hint_2=proxy_hint(fallback_2) if fallback_2 else None,
        key_version=profile.key_version,
        health_status=profile.health_status,
        health_reason_code=profile.health_reason_code,
        last_tested_at=profile.last_tested_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


async def list_proxy_profiles(
    session: AsyncSession,
    cipher: AccountSecretCipher,
) -> list[ProxyProfileRead]:
    rows = list((await session.scalars(select(ProxyProfile).order_by(ProxyProfile.name))).all())
    return [serialize_proxy_profile(row, cipher) for row in rows]


async def probe_proxy_profile(
    session: AsyncSession,
    profile_id: uuid.UUID,
    cipher: AccountSecretCipher,
) -> ProxyProbeRead:
    profile = await session.get(ProxyProfile, profile_id)
    if not profile:
        raise ApiProblem(
            status=404,
            code="PROXY_PROFILE_NOT_FOUND",
            title="Proxy profile not found",
            detail=f"No proxy profile exists with id {profile_id}.",
        )
    urls = [
        value
        for value in (
            _decrypt_url(cipher, profile, "primary_url"),
            _decrypt_url(cipher, profile, "fallback_url_1"),
            _decrypt_url(cipher, profile, "fallback_url_2"),
        )
        if value and value != "direct"
    ]
    if not urls:
        raise ApiProblem(
            status=409,
            code="PROXY_ENDPOINT_MISSING",
            title="Proxy endpoint is missing",
            detail="This profile has no network proxy endpoint to probe.",
        )
    await session.commit()
    attempts: list[ProxyProbeAttemptRead] = []
    first_success_index: int | None = None
    for index, url in enumerate(urls):
        result = await PROXY_PROBER.probe(url)
        attempts.append(
            ProxyProbeAttemptRead(
                endpoint_hint=proxy_hint(url),
                success=result.success,
                reason_code=result.reason_code,
                latency_ms=result.latency_ms,
                message=result.message,
            )
        )
        if result.success:
            first_success_index = index
            break
    tested_at = datetime.now(UTC)
    status = "healthy" if first_success_index is not None else "failed"
    if first_success_index == 0:
        reason_code = "PROXY_PRIMARY_OK"
    elif first_success_index is not None:
        reason_code = "PROXY_FALLBACK_OK"
    else:
        reason_code = "ALL_PROXY_ENDPOINTS_FAILED"
    profile = await session.get(ProxyProfile, profile_id, with_for_update=True)
    if profile:
        profile.health_status = status
        profile.health_reason_code = reason_code
        profile.last_tested_at = tested_at
    await session.execute(
        update(Account).where(Account.proxy_profile_id == profile_id).values(proxy_health_status=status)
    )
    await session.commit()
    return ProxyProbeRead(
        profile_id=profile_id,
        status=status,
        reason_code=reason_code,
        attempts=attempts,
        tested_at=tested_at,
    )


async def assign_account_proxy(
    session: AsyncSession,
    account_id: uuid.UUID,
    profile_id: uuid.UUID | None,
) -> None:
    account = await session.get(Account, account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    if profile_id and not await session.get(ProxyProfile, profile_id):
        raise ApiProblem(
            status=404,
            code="PROXY_PROFILE_NOT_FOUND",
            title="Proxy profile not found",
            detail=f"No proxy profile exists with id {profile_id}.",
        )
    account.proxy_profile_id = profile_id
    account.proxy_health_status = "unknown" if profile_id else "not_configured"
    account.row_version += 1
    await session.commit()


async def assign_group_proxy(
    session: AsyncSession,
    group_id: uuid.UUID,
    profile_id: uuid.UUID | None,
) -> None:
    group = await session.get(Group, group_id)
    if not group:
        raise ApiProblem(
            status=404,
            code="GROUP_NOT_FOUND",
            title="Group not found",
            detail=f"No group exists with id {group_id}.",
        )
    if profile_id and not await session.get(ProxyProfile, profile_id):
        raise ApiProblem(
            status=404,
            code="PROXY_PROFILE_NOT_FOUND",
            title="Proxy profile not found",
            detail=f"No proxy profile exists with id {profile_id}.",
        )
    group.proxy_profile_id = profile_id
    await session.commit()


def _mail_placeholder(email: str) -> str:
    local_part = email.split("@", 1)[0]
    normalized = re.sub(r"[^a-zA-Z0-9]", "", local_part).lower()
    return normalized or "mail"


async def resolve_account_proxy(
    session: AsyncSession,
    account_id: uuid.UUID,
    cipher: AccountSecretCipher,
) -> ResolvedProxy:
    account = await session.get(Account, account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    profile: ProxyProfile | None = None
    source: Literal["account", "group", "none"] = "none"
    source_group_id: uuid.UUID | None = None
    if account.proxy_profile_id:
        candidate = await session.get(ProxyProfile, account.proxy_profile_id)
        if candidate and candidate.enabled:
            profile = candidate
            source = "account"
    group_id = account.group_id
    while profile is None and group_id:
        group = await session.get(Group, group_id)
        if not group:
            break
        if group.proxy_profile_id:
            candidate = await session.get(ProxyProfile, group.proxy_profile_id)
            if candidate and candidate.enabled:
                profile = candidate
                source = "group"
                source_group_id = group.id
                break
        group_id = group.parent_id
    if profile is None:
        return ResolvedProxy(account.id, source, source_group_id, None, None, ())
    placeholder = _mail_placeholder(account.email)
    urls = tuple(
        value.replace("{mail}", placeholder)
        for value in (
            _decrypt_url(cipher, profile, "primary_url"),
            _decrypt_url(cipher, profile, "fallback_url_1"),
            _decrypt_url(cipher, profile, "fallback_url_2"),
        )
        if value
    )
    return ResolvedProxy(
        account.id,
        source,
        source_group_id,
        profile.id,
        profile.name,
        urls,
    )


def serialize_resolved_proxy(resolved: ResolvedProxy) -> ResolvedProxyRead:
    return ResolvedProxyRead(
        account_id=resolved.account_id,
        source=resolved.source,
        source_group_id=resolved.source_group_id,
        proxy_profile_id=resolved.profile_id,
        profile_name=resolved.profile_name,
        endpoint_hints=[proxy_hint(value) for value in resolved.urls],
    )


async def delete_proxy_profile(session: AsyncSession, profile_id: uuid.UUID) -> None:
    await session.execute(
        update(Account)
        .where(Account.proxy_profile_id == profile_id)
        .values(
            proxy_profile_id=None,
            proxy_health_status="not_configured",
            row_version=Account.row_version + 1,
        )
    )
    await session.execute(
        update(Group).where(Group.proxy_profile_id == profile_id).values(proxy_profile_id=None)
    )
    result = await session.execute(delete(ProxyProfile).where(ProxyProfile.id == profile_id))
    if not result.rowcount:  # type: ignore[attr-defined]
        raise ApiProblem(
            status=404,
            code="PROXY_PROFILE_NOT_FOUND",
            title="Proxy profile not found",
            detail=f"No proxy profile exists with id {profile_id}.",
        )
    await session.commit()
