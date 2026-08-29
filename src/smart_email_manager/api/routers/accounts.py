import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.accounts import (
    AccountArchiveRequest,
    AccountBulkExecute,
    AccountBulkMutation,
    AccountBulkPreviewCreate,
    AccountBulkPreviewRead,
    AccountBulkResult,
    AccountCreate,
    AccountListItem,
    AccountPage,
    AccountUpdate,
)
from smart_email_manager.api.schemas.secrets import AccountSecretsStatus, AccountSecretsWrite
from smart_email_manager.config import get_settings
from smart_email_manager.security.encryption import AccountSecretCipher
from smart_email_manager.services.accounts import (
    archive_account,
    bulk_mutate_accounts,
    create_account,
    get_account_or_404,
    list_accounts,
    purge_account,
    update_account,
)
from smart_email_manager.services.bulk import create_bulk_preview, execute_bulk_preview
from smart_email_manager.services.secrets import get_account_secret_status, write_account_secrets
from smart_email_manager.services.views import resolve_account_view_filters

router = APIRouter(prefix="/accounts", tags=["accounts"])
AccountsRead = Annotated[object, Depends(require_scopes("accounts:read"))]
AccountsWrite = Annotated[object, Depends(require_scopes("accounts:write"))]
AccountSecretsWriteAuth = Annotated[object, Depends(require_scopes("accounts:secrets:write"))]


@router.post(
    "",
    operation_id="create_account",
    response_model=AccountListItem,
    status_code=201,
    summary="Create a mailbox account without secrets",
)
async def post_account(
    payload: AccountCreate,
    session: SessionDependency,
    _auth: AccountsWrite,
) -> AccountListItem:
    return AccountListItem.model_validate(await create_account(session, payload))


@router.get(
    "/{account_id}",
    operation_id="get_account",
    response_model=AccountListItem,
)
async def get_account(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: AccountsRead,
) -> AccountListItem:
    return AccountListItem.model_validate(await get_account_or_404(session, account_id))


@router.patch(
    "/{account_id}",
    operation_id="update_account",
    response_model=AccountListItem,
)
async def patch_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    session: SessionDependency,
    _auth: AccountsWrite,
) -> AccountListItem:
    return AccountListItem.model_validate(await update_account(session, account_id, payload))


@router.post(
    "/{account_id}/archive",
    operation_id="archive_account",
    response_model=AccountListItem,
)
async def post_archive_account(
    account_id: uuid.UUID,
    payload: AccountArchiveRequest,
    session: SessionDependency,
    _auth: AccountsWrite,
) -> AccountListItem:
    return AccountListItem.model_validate(await archive_account(session, account_id, payload))


@router.delete("/{account_id}", operation_id="purge_account", status_code=204)
async def delete_account(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: AccountsWrite,
    confirm_email: Annotated[str, Query(min_length=3, max_length=320)],
) -> Response:
    await purge_account(session, account_id, confirm_email=confirm_email)
    return Response(status_code=204)


@router.post(
    "/bulk/mutations",
    operation_id="bulk_mutate_accounts",
    response_model=AccountBulkResult,
)
async def post_bulk_mutation(
    payload: AccountBulkMutation,
    session: SessionDependency,
    _auth: AccountsWrite,
) -> AccountBulkResult:
    return await bulk_mutate_accounts(session, payload)


@router.post(
    "/bulk/previews",
    operation_id="create_account_bulk_preview",
    response_model=AccountBulkPreviewRead,
    status_code=201,
    summary="Freeze a stable bulk selection and preview its impact",
)
async def post_bulk_preview(
    payload: AccountBulkPreviewCreate,
    session: SessionDependency,
    _auth: AccountsWrite,
) -> AccountBulkPreviewRead:
    return await create_bulk_preview(session, payload)


@router.post(
    "/bulk/executions",
    operation_id="execute_account_bulk_preview",
    response_model=AccountBulkResult,
    summary="Execute a single-use stable bulk preview",
)
async def post_bulk_execution(
    payload: AccountBulkExecute,
    session: SessionDependency,
    _auth: AccountsWrite,
) -> AccountBulkResult:
    return await execute_bulk_preview(session, payload)


@router.get(
    "/{account_id}/secrets/status",
    operation_id="get_account_secrets_status",
    response_model=AccountSecretsStatus,
    summary="Read account secret presence without returning plaintext",
)
async def account_secrets_status(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: AccountsRead,
) -> AccountSecretsStatus:
    return await get_account_secret_status(session, account_id)


@router.put(
    "/{account_id}/secrets",
    operation_id="write_account_secrets",
    response_model=AccountSecretsStatus,
    summary="Encrypt and store account secrets without returning plaintext",
)
async def put_account_secrets(
    account_id: uuid.UUID,
    payload: AccountSecretsWrite,
    session: SessionDependency,
    _auth: AccountSecretsWriteAuth,
) -> AccountSecretsStatus:
    return await write_account_secrets(
        session,
        account_id=account_id,
        payload=payload,
        cipher=AccountSecretCipher.from_settings(get_settings()),
    )


@router.get(
    "",
    operation_id="list_accounts",
    response_model=AccountPage,
    summary="List mailbox accounts with stable cursor pagination",
)
async def get_accounts(
    session: SessionDependency,
    _auth: AccountsRead,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: str | None = None,
    lifecycle_status: str | None = None,
    token_status: str | None = None,
    mail_health_status: str | None = None,
    query: Annotated[str | None, Query(max_length=320)] = None,
    view: Annotated[str | None, Query(max_length=64)] = None,
    saved_view_id: uuid.UUID | None = None,
) -> AccountPage:
    view_filters = await resolve_account_view_filters(
        session,
        builtin_key=view,
        saved_view_id=saved_view_id,
    )
    accounts, next_cursor = await list_accounts(
        session,
        limit=limit,
        cursor=cursor,
        lifecycle_status=lifecycle_status,
        token_status=token_status,
        mail_health_status=mail_health_status,
        query=query,
        view_filters=view_filters,
    )
    return AccountPage(
        items=[AccountListItem.model_validate(account) for account in accounts],
        next_cursor=next_cursor,
        limit=limit,
    )
