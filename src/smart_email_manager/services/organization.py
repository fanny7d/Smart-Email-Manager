from __future__ import annotations

import uuid
from collections import defaultdict
from typing import cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.organization import (
    AccountTagMutation,
    AliasesReplace,
    GroupCreate,
    GroupRead,
    GroupUpdate,
    TagCreate,
)
from smart_email_manager.db.models import Account, AccountAlias, AccountTag, Group, Tag


async def get_default_group_id(session: AsyncSession) -> uuid.UUID | None:
    return cast(
        uuid.UUID | None,
        await session.scalar(select(Group.id).where(Group.system_key == "default")),
    )


async def get_group_or_404(session: AsyncSession, group_id: uuid.UUID) -> Group:
    group = await session.get(Group, group_id)
    if not group:
        raise ApiProblem(
            status=404,
            code="GROUP_NOT_FOUND",
            title="Group not found",
            detail=f"No group exists with id {group_id}.",
        )
    return group


async def _group_tree_data(
    session: AsyncSession,
) -> tuple[list[Group], dict[uuid.UUID | None, list[Group]]]:
    groups = list(
        (await session.scalars(select(Group).order_by(Group.level, Group.sort_order, Group.name))).all()
    )
    children: dict[uuid.UUID | None, list[Group]] = defaultdict(list)
    for group in groups:
        children[group.parent_id].append(group)
    return groups, children


def _descendant_ids(group_id: uuid.UUID, children: dict[uuid.UUID | None, list[Group]]) -> list[uuid.UUID]:
    result = [group_id]
    for child in children.get(group_id, []):
        result.extend(_descendant_ids(child.id, children))
    return result


async def list_groups(session: AsyncSession) -> list[GroupRead]:
    groups, children = await _group_tree_data(session)
    count_rows = (
        await session.execute(select(Account.group_id, func.count()).group_by(Account.group_id))
    ).all()
    account_counts: dict[uuid.UUID | None, int] = {group_id: int(count) for group_id, count in count_rows}
    result: list[GroupRead] = []
    for group in groups:
        descendants = _descendant_ids(group.id, children)
        result.append(
            GroupRead(
                id=group.id,
                name=group.name,
                description=group.description,
                color=group.color,
                sort_order=group.sort_order,
                level=group.level,
                parent_id=group.parent_id,
                system_key=group.system_key,
                direct_account_count=int(account_counts.get(group.id, 0)),
                descendant_account_count=sum(int(account_counts.get(item, 0)) for item in descendants),
                created_at=group.created_at,
                updated_at=group.updated_at,
            )
        )
    return result


async def create_group(session: AsyncSession, payload: GroupCreate) -> Group:
    parent = await get_group_or_404(session, payload.parent_id) if payload.parent_id else None
    if parent and (parent.level >= 3 or parent.system_key == "temporary"):
        raise ApiProblem(
            status=409,
            code="GROUP_DEPTH_EXCEEDED",
            title="Group cannot accept children",
            detail="Groups support at most three levels and temporary mail is a system leaf.",
        )
    sibling_max = (
        await session.scalar(
            select(func.max(Group.sort_order)).where(Group.parent_id == (parent.id if parent else None))
        )
        or 0
    )
    group = Group(
        name=payload.name.strip(),
        description=payload.description.strip(),
        color=payload.color,
        parent_id=parent.id if parent else None,
        level=(parent.level + 1) if parent else 1,
        sort_order=sibling_max + 1,
    )
    session.add(group)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="GROUP_NAME_CONFLICT",
            title="Group name already exists",
            detail=f"A group already uses the name {payload.name.strip()}.",
        ) from exc
    await session.refresh(group)
    return group


def _subtree_depth(group_id: uuid.UUID, children: dict[uuid.UUID | None, list[Group]]) -> int:
    child_depths = [_subtree_depth(child.id, children) for child in children.get(group_id, [])]
    return 1 + (max(child_depths) if child_depths else 0)


async def update_group(session: AsyncSession, group_id: uuid.UUID, payload: GroupUpdate) -> Group:
    group = await get_group_or_404(session, group_id)
    if group.system_key and "parent_id" in payload.model_fields_set and payload.parent_id is not None:
        raise ApiProblem(
            status=409,
            code="SYSTEM_GROUP_IMMUTABLE",
            title="System group cannot be moved",
            detail="System groups must remain at the root level.",
        )
    if payload.name is not None:
        group.name = payload.name.strip()
    if payload.description is not None:
        group.description = payload.description.strip()
    if payload.color is not None:
        group.color = payload.color
    if payload.sort_order is not None:
        group.sort_order = payload.sort_order

    if "parent_id" in payload.model_fields_set:
        parent = await get_group_or_404(session, payload.parent_id) if payload.parent_id else None
        groups, children = await _group_tree_data(session)
        descendants = set(_descendant_ids(group.id, children))
        if parent and parent.id in descendants:
            raise ApiProblem(
                status=409,
                code="GROUP_CYCLE",
                title="Group move would create a cycle",
                detail="A group cannot be moved below its own descendant.",
            )
        target_level = parent.level + 1 if parent else 1
        if parent and parent.system_key == "temporary":
            target_level = 4
        if target_level + _subtree_depth(group.id, children) - 1 > 3:
            raise ApiProblem(
                status=409,
                code="GROUP_DEPTH_EXCEEDED",
                title="Group move exceeds depth limit",
                detail="The moved group subtree would exceed three levels.",
            )
        level_delta = target_level - group.level
        for item in groups:
            if item.id in descendants:
                item.level += level_delta
        group.parent_id = parent.id if parent else None

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="GROUP_NAME_CONFLICT",
            title="Group name already exists",
            detail="Group names must be unique.",
        ) from exc
    await session.refresh(group)
    return group


async def delete_group(session: AsyncSession, group_id: uuid.UUID) -> int:
    group = await get_group_or_404(session, group_id)
    if group.system_key:
        raise ApiProblem(
            status=409,
            code="SYSTEM_GROUP_IMMUTABLE",
            title="System group cannot be deleted",
            detail="Default and temporary system groups are permanent.",
        )
    _groups, children = await _group_tree_data(session)
    subtree = _descendant_ids(group.id, children)
    default_group_id = await get_default_group_id(session)
    await session.execute(
        update(Account).where(Account.group_id.in_(subtree)).values(group_id=default_group_id)
    )
    deleted = 0
    for child_id in reversed(subtree):
        result = await session.execute(delete(Group).where(Group.id == child_id))
        deleted += int(result.rowcount or 0)  # type: ignore[attr-defined]
    await session.commit()
    return deleted


async def create_tag(session: AsyncSession, payload: TagCreate) -> Tag:
    tag = Tag(name=payload.name.strip(), color=payload.color)
    session.add(tag)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="TAG_NAME_CONFLICT",
            title="Tag name already exists",
            detail=f"A tag already uses the name {payload.name.strip()}.",
        ) from exc
    await session.refresh(tag)
    return tag


async def list_account_tags(session: AsyncSession, account_id: uuid.UUID) -> list[Tag]:
    if not await session.get(Account, account_id):
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    return list(
        (
            await session.scalars(
                select(Tag)
                .join(AccountTag, AccountTag.tag_id == Tag.id)
                .where(AccountTag.account_id == account_id)
                .order_by(Tag.name)
            )
        ).all()
    )


async def mutate_account_tags(
    session: AsyncSession,
    account_id: uuid.UUID,
    payload: AccountTagMutation,
) -> list[Tag]:
    account = await session.get(Account, account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    existing_tag_ids = set((await session.scalars(select(Tag.id).where(Tag.id.in_(payload.tag_ids)))).all())
    if existing_tag_ids != set(payload.tag_ids):
        raise ApiProblem(
            status=404,
            code="TAG_NOT_FOUND",
            title="Tag not found",
            detail="At least one requested tag does not exist.",
        )
    if payload.action == "replace":
        await session.execute(delete(AccountTag).where(AccountTag.account_id == account_id))
    if payload.action == "remove":
        await session.execute(
            delete(AccountTag).where(
                AccountTag.account_id == account_id,
                AccountTag.tag_id.in_(payload.tag_ids),
            )
        )
    else:
        current = set(
            (
                await session.scalars(select(AccountTag.tag_id).where(AccountTag.account_id == account_id))
            ).all()
        )
        for tag_id in existing_tag_ids - current:
            session.add(AccountTag(account_id=account_id, tag_id=tag_id))
    account.row_version += 1
    await session.commit()
    return list(
        (
            await session.scalars(
                select(Tag)
                .join(AccountTag, AccountTag.tag_id == Tag.id)
                .where(AccountTag.account_id == account_id)
                .order_by(Tag.name)
            )
        ).all()
    )


async def replace_account_aliases(
    session: AsyncSession,
    account_id: uuid.UUID,
    payload: AliasesReplace,
) -> list[AccountAlias]:
    account = await session.get(Account, account_id)
    if not account:
        raise ApiProblem(
            status=404,
            code="ACCOUNT_NOT_FOUND",
            title="Account not found",
            detail=f"No account exists with id {account_id}.",
        )
    normalized = [str(value).strip().lower() for value in payload.aliases]
    if account.email_normalized in normalized or len(normalized) != len(set(normalized)):
        raise ApiProblem(
            status=409,
            code="ALIAS_CONFLICT",
            title="Alias conflicts with account data",
            detail="Aliases must be unique and cannot equal the primary email.",
        )
    conflicts = await session.scalar(
        select(func.count())
        .select_from(Account)
        .where(Account.email_normalized.in_(normalized), Account.id != account_id)
    )
    alias_conflicts = await session.scalar(
        select(func.count())
        .select_from(AccountAlias)
        .where(AccountAlias.email_normalized.in_(normalized), AccountAlias.account_id != account_id)
    )
    if conflicts or alias_conflicts:
        raise ApiProblem(
            status=409,
            code="ALIAS_CONFLICT",
            title="Alias is already in use",
            detail="An alias conflicts with another primary account or alias.",
        )
    await session.execute(delete(AccountAlias).where(AccountAlias.account_id == account_id))
    rows = [
        AccountAlias(
            account_id=account_id,
            email=str(value).strip(),
            email_normalized=str(value).strip().lower(),
        )
        for value in payload.aliases
    ]
    session.add_all(rows)
    account.row_version += 1
    await session.commit()
    return list(
        (
            await session.scalars(
                select(AccountAlias)
                .where(AccountAlias.account_id == account_id)
                .order_by(AccountAlias.email_normalized)
            )
        ).all()
    )
