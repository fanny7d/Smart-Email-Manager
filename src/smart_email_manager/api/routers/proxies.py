from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.proxies import (
    ProxyAssignment,
    ProxyProbeRead,
    ProxyProfileRead,
    ProxyProfileWrite,
    ResolvedProxyRead,
)
from smart_email_manager.config import get_settings
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.proxies import (
    assign_account_proxy,
    assign_group_proxy,
    delete_proxy_profile,
    list_proxy_profiles,
    probe_proxy_profile,
    resolve_account_proxy,
    serialize_proxy_profile,
    serialize_resolved_proxy,
    write_proxy_profile,
)

router = APIRouter(prefix="/proxies", tags=["proxies"])
ProxyRead = Annotated[object, Depends(require_scopes("proxies:read"))]
ProxyWrite = Annotated[object, Depends(require_scopes("proxies:write"))]


def _cipher() -> AccountSecretCipher:
    return AccountSecretCipher.from_settings(get_settings())


@router.get("", operation_id="list_proxy_profiles", response_model=list[ProxyProfileRead])
async def get_profiles(session: SessionDependency, _auth: ProxyRead) -> list[ProxyProfileRead]:
    return await list_proxy_profiles(session, _cipher())


@router.post(
    "",
    operation_id="create_proxy_profile",
    response_model=ProxyProfileRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_profile(
    payload: ProxyProfileWrite,
    session: SessionDependency,
    _auth: ProxyWrite,
) -> ProxyProfileRead:
    return serialize_proxy_profile(
        await write_proxy_profile(session, payload=payload, cipher=_cipher()),
        _cipher(),
    )


@router.put("/{profile_id}", operation_id="update_proxy_profile", response_model=ProxyProfileRead)
async def put_profile(
    profile_id: uuid.UUID,
    payload: ProxyProfileWrite,
    session: SessionDependency,
    _auth: ProxyWrite,
) -> ProxyProfileRead:
    cipher = _cipher()
    return serialize_proxy_profile(
        await write_proxy_profile(
            session,
            payload=payload,
            cipher=cipher,
            profile_id=profile_id,
        ),
        cipher,
    )


@router.post(
    "/{profile_id}/probe",
    operation_id="probe_proxy_profile",
    response_model=ProxyProbeRead,
)
async def post_probe_profile(
    profile_id: uuid.UUID,
    session: SessionDependency,
    _auth: ProxyWrite,
) -> ProxyProbeRead:
    return await probe_proxy_profile(session, profile_id, _cipher())


@router.delete("/{profile_id}", operation_id="delete_proxy_profile", status_code=204)
async def remove_profile(
    profile_id: uuid.UUID,
    session: SessionDependency,
    _auth: ProxyWrite,
) -> Response:
    await delete_proxy_profile(session, profile_id)
    return Response(status_code=204)


@router.put(
    "/accounts/{account_id}",
    operation_id="assign_account_proxy",
    status_code=204,
)
async def put_account_proxy(
    account_id: uuid.UUID,
    payload: ProxyAssignment,
    session: SessionDependency,
    _auth: ProxyWrite,
) -> Response:
    await assign_account_proxy(session, account_id, payload.proxy_profile_id)
    return Response(status_code=204)


@router.put(
    "/groups/{group_id}",
    operation_id="assign_group_proxy",
    status_code=204,
)
async def put_group_proxy(
    group_id: uuid.UUID,
    payload: ProxyAssignment,
    session: SessionDependency,
    _auth: ProxyWrite,
) -> Response:
    await assign_group_proxy(session, group_id, payload.proxy_profile_id)
    return Response(status_code=204)


@router.get(
    "/accounts/{account_id}/resolved",
    operation_id="resolve_account_proxy",
    response_model=ResolvedProxyRead,
)
async def get_resolved_account_proxy(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: ProxyRead,
) -> ResolvedProxyRead:
    return serialize_resolved_proxy(await resolve_account_proxy(session, account_id, _cipher()))
