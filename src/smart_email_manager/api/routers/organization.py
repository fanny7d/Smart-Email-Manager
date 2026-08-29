from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.organization import (
    AccountTagMutation,
    AliasesReplace,
    AliasRead,
    GroupCreate,
    GroupRead,
    GroupUpdate,
    TagCreate,
    TagRead,
)
from smart_email_manager.db.models import AccountAlias, Tag
from smart_email_manager.services.organization import (
    create_group,
    create_tag,
    delete_group,
    list_account_tags,
    list_groups,
    mutate_account_tags,
    replace_account_aliases,
    update_group,
)

router = APIRouter(tags=["organization"])
OrganizationRead = Annotated[object, Depends(require_scopes("organization:read"))]
OrganizationWrite = Annotated[object, Depends(require_scopes("organization:write"))]


@router.get("/groups", operation_id="list_groups", response_model=list[GroupRead])
async def get_groups(session: SessionDependency, _auth: OrganizationRead) -> list[GroupRead]:
    return await list_groups(session)


@router.post(
    "/groups",
    operation_id="create_group",
    response_model=GroupRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_group(
    payload: GroupCreate,
    session: SessionDependency,
    _auth: OrganizationWrite,
) -> GroupRead:
    group = await create_group(session, payload)
    return GroupRead.model_validate(group)


@router.put("/groups/{group_id}", operation_id="update_group", response_model=GroupRead)
async def put_group(
    group_id: uuid.UUID,
    payload: GroupUpdate,
    session: SessionDependency,
    _auth: OrganizationWrite,
) -> GroupRead:
    return GroupRead.model_validate(await update_group(session, group_id, payload))


@router.delete("/groups/{group_id}", operation_id="delete_group", status_code=204)
async def remove_group(
    group_id: uuid.UUID,
    session: SessionDependency,
    _auth: OrganizationWrite,
) -> Response:
    await delete_group(session, group_id)
    return Response(status_code=204)


@router.get("/tags", operation_id="list_tags", response_model=list[TagRead])
async def get_tags(session: SessionDependency, _auth: OrganizationRead) -> list[TagRead]:
    rows = list((await session.scalars(select(Tag).order_by(Tag.name))).all())
    return [TagRead.model_validate(row) for row in rows]


@router.post(
    "/tags",
    operation_id="create_tag",
    response_model=TagRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_tag(
    payload: TagCreate,
    session: SessionDependency,
    _auth: OrganizationWrite,
) -> TagRead:
    return TagRead.model_validate(await create_tag(session, payload))


@router.delete("/tags/{tag_id}", operation_id="delete_tag", status_code=204)
async def remove_tag(
    tag_id: uuid.UUID,
    session: SessionDependency,
    _auth: OrganizationWrite,
) -> Response:
    result = await session.execute(delete(Tag).where(Tag.id == tag_id))
    if not result.rowcount:  # type: ignore[attr-defined]
        raise ApiProblem(
            status=404,
            code="TAG_NOT_FOUND",
            title="Tag not found",
            detail=f"No tag exists with id {tag_id}.",
        )
    await session.commit()
    return Response(status_code=204)


@router.put(
    "/accounts/{account_id}/tags",
    operation_id="mutate_account_tags",
    response_model=list[TagRead],
)
async def put_account_tags(
    account_id: uuid.UUID,
    payload: AccountTagMutation,
    session: SessionDependency,
    _auth: OrganizationWrite,
) -> list[TagRead]:
    return [TagRead.model_validate(row) for row in await mutate_account_tags(session, account_id, payload)]


@router.get(
    "/accounts/{account_id}/tags",
    operation_id="list_account_tags",
    response_model=list[TagRead],
)
async def get_account_tags(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: OrganizationRead,
) -> list[TagRead]:
    return [TagRead.model_validate(row) for row in await list_account_tags(session, account_id)]


@router.get(
    "/accounts/{account_id}/aliases",
    operation_id="list_account_aliases",
    response_model=list[AliasRead],
)
async def get_account_aliases(
    account_id: uuid.UUID,
    session: SessionDependency,
    _auth: OrganizationRead,
) -> list[AliasRead]:
    rows = list(
        (
            await session.scalars(
                select(AccountAlias)
                .where(AccountAlias.account_id == account_id)
                .order_by(AccountAlias.email_normalized)
            )
        ).all()
    )
    return [AliasRead.model_validate(row) for row in rows]


@router.put(
    "/accounts/{account_id}/aliases",
    operation_id="replace_account_aliases",
    response_model=list[AliasRead],
)
async def put_account_aliases(
    account_id: uuid.UUID,
    payload: AliasesReplace,
    session: SessionDependency,
    _auth: OrganizationWrite,
) -> list[AliasRead]:
    return [
        AliasRead.model_validate(row) for row in await replace_account_aliases(session, account_id, payload)
    ]
