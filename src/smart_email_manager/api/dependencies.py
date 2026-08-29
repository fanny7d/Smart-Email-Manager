from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.config import Settings, get_settings
from smart_email_manager.db.session import get_session
from smart_email_manager.security.tokens import (
    ApiPrincipal,
    active_persistent_token_count,
    authenticate_persistent_token,
)

SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


async def authenticate_api_token(
    session: SessionDependency,
    settings: SettingsDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> ApiPrincipal:
    configured = settings.api_token.get_secret_value() if settings.api_token else ""
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() == "bearer" and supplied:
        if configured and secrets.compare_digest(supplied, configured):
            return ApiPrincipal(None, "environment bootstrap", frozenset({"*"}), "environment")
        persistent = await authenticate_persistent_token(session, supplied)
        if persistent:
            return persistent

    if (
        not configured
        and settings.environment in {"development", "test"}
        and await active_persistent_token_count(session) == 0
    ):
        return ApiPrincipal(None, "development bootstrap", frozenset({"*"}), "development")

    raise ApiProblem(
        status=401,
        code="INVALID_API_TOKEN",
        title="Authentication failed",
        detail="Provide a valid bearer token.",
    )


PrincipalDependency = Annotated[ApiPrincipal, Depends(authenticate_api_token)]


def require_scopes(*required_scopes: str) -> Callable[[ApiPrincipal], Awaitable[ApiPrincipal]]:
    required = set(required_scopes)

    async def dependency(principal: PrincipalDependency) -> ApiPrincipal:
        if not principal.allows(required):
            raise ApiProblem(
                status=403,
                code="INSUFFICIENT_SCOPE",
                title="Insufficient API token scope",
                detail=f"This operation requires: {', '.join(sorted(required))}.",
                context={"required_scopes": sorted(required)},
            )
        return principal

    return dependency


AuthDependency = PrincipalDependency
