from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.db.models import ApiToken

TOKEN_PREFIX = "sem"


@dataclass(frozen=True)
class ApiPrincipal:
    token_id: uuid.UUID | None
    name: str
    scopes: frozenset[str]
    source: str

    def allows(self, required: set[str]) -> bool:
        return "*" in self.scopes or required.issubset(self.scopes)


def hash_api_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def parse_token_prefix(token: str) -> str | None:
    parts = token.split("_", 2)
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return None
    return parts[1]


def generate_api_token() -> tuple[str, str]:
    prefix = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8]
    secret = secrets.token_urlsafe(32)
    return f"{TOKEN_PREFIX}_{prefix}_{secret}", prefix


async def active_persistent_token_count(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    return (
        await session.scalar(
            select(func.count())
            .select_from(ApiToken)
            .where(
                ApiToken.revoked_at.is_(None),
                (ApiToken.expires_at.is_(None) | (ApiToken.expires_at > now)),
            )
        )
        or 0
    )


async def authenticate_persistent_token(session: AsyncSession, token: str) -> ApiPrincipal | None:
    prefix = parse_token_prefix(token)
    if not prefix:
        return None
    candidates = list((await session.scalars(select(ApiToken).where(ApiToken.token_prefix == prefix))).all())
    supplied_hash = hash_api_token(token)
    now = datetime.now(UTC)
    for candidate in candidates:
        if candidate.revoked_at or (candidate.expires_at and candidate.expires_at <= now):
            continue
        if secrets.compare_digest(candidate.token_hash, supplied_hash):
            candidate.last_used_at = now
            await session.commit()
            return ApiPrincipal(
                token_id=candidate.id,
                name=candidate.name,
                scopes=frozenset(candidate.scopes),
                source="persistent",
            )
    return None


async def create_persistent_token(
    session: AsyncSession,
    *,
    name: str,
    scopes: list[str],
    expires_in_days: int | None,
) -> tuple[ApiToken, str]:
    token, prefix = generate_api_token()
    expires_at = datetime.now(UTC) + timedelta(days=expires_in_days) if expires_in_days else None
    row = ApiToken(
        name=name.strip(),
        token_prefix=prefix,
        token_hash=hash_api_token(token),
        scopes=sorted(set(scopes)),
        expires_at=expires_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, token


async def revoke_persistent_token(session: AsyncSession, token_id: uuid.UUID) -> ApiToken:
    row = await session.get(ApiToken, token_id)
    if not row:
        raise ApiProblem(
            status=404,
            code="API_TOKEN_NOT_FOUND",
            title="API token not found",
            detail=f"No API token exists with id {token_id}.",
        )
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
    return row
