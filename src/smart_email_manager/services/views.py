from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.problems import ApiProblem
from smart_email_manager.api.schemas.views import (
    AccountViewFilters,
    BuiltinAccountViewRead,
    SavedAccountViewCreate,
    SavedAccountViewUpdate,
)
from smart_email_manager.db.models import SavedAccountView


def builtin_account_views(now: datetime | None = None) -> list[BuiltinAccountViewRead]:
    stale_before = (now or datetime.now(UTC)) - timedelta(days=30)
    definitions = (
        (
            "pending_verification",
            "待验证",
            "尚未完成授权或连通性验证",
            AccountViewFilters(authorization_statuses=["unknown", "pending"]),
        ),
        (
            "healthy",
            "正常",
            "启用且授权、Token、邮件均健康",
            AccountViewFilters(
                lifecycle_statuses=["active"],
                authorization_statuses=["valid"],
                token_statuses=["success"],
                mail_health_statuses=["healthy"],
            ),
        ),
        (
            "reauthorization",
            "需重新授权",
            "授权失效或明确要求重新授权",
            AccountViewFilters(authorization_statuses=["invalid", "reauthorization_required"]),
        ),
        (
            "token_failed",
            "Token 异常",
            "Token 刷新失败或状态过旧",
            AccountViewFilters(token_statuses=["failed", "stale"]),
        ),
        (
            "proxy_failed",
            "代理异常",
            "账号解析后的代理健康检查失败",
            AccountViewFilters(proxy_health_statuses=["failed"]),
        ),
        (
            "consecutive_failures",
            "连续失败",
            "至少连续失败两次",
            AccountViewFilters(min_consecutive_failures=2),
        ),
        (
            "stale_mail",
            "长期未成功拉信",
            "超过 30 天没有成功读取邮箱",
            AccountViewFilters(last_mail_success_before=stale_before),
        ),
        (
            "inactive",
            "已停用或归档",
            "生命周期不再处于启用状态",
            AccountViewFilters(lifecycle_statuses=["inactive", "archived"]),
        ),
        ("ungrouped", "未分组", "没有稳定业务分组的账号", AccountViewFilters(ungrouped=True)),
        ("untagged", "未打标签", "没有任何人工标签的账号", AccountViewFilters(untagged=True)),
    )
    return [
        BuiltinAccountViewRead(key=key, name=name, description=description, filters=filters)
        for key, name, description, filters in definitions
    ]


async def list_saved_account_views(session: AsyncSession) -> list[SavedAccountView]:
    return list(
        (
            await session.scalars(
                select(SavedAccountView).order_by(
                    SavedAccountView.sort_order,
                    SavedAccountView.created_at,
                    SavedAccountView.id,
                )
            )
        ).all()
    )


async def get_saved_account_view_or_404(
    session: AsyncSession,
    view_id: uuid.UUID,
    *,
    lock: bool = False,
) -> SavedAccountView:
    statement = select(SavedAccountView).where(SavedAccountView.id == view_id)
    if lock:
        statement = statement.with_for_update()
    view = await session.scalar(statement)
    if not view:
        raise ApiProblem(
            status=404,
            code="SAVED_VIEW_NOT_FOUND",
            title="Saved account view not found",
            detail=f"No saved account view exists with id {view_id}.",
        )
    return view


async def create_saved_account_view(
    session: AsyncSession,
    payload: SavedAccountViewCreate,
) -> SavedAccountView:
    view = SavedAccountView(
        name=payload.name.strip(),
        filters=payload.filters.model_dump(mode="json", exclude_none=True),
        sort_order=payload.sort_order,
    )
    session.add(view)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="SAVED_VIEW_NAME_CONFLICT",
            title="Saved account view already exists",
            detail=f"A saved account view already uses {payload.name.strip()}.",
        ) from exc
    await session.refresh(view)
    return view


async def update_saved_account_view(
    session: AsyncSession,
    view_id: uuid.UUID,
    payload: SavedAccountViewUpdate,
) -> SavedAccountView:
    view = await get_saved_account_view_or_404(session, view_id, lock=True)
    if payload.name is not None:
        view.name = payload.name.strip()
    if payload.filters is not None:
        view.filters = payload.filters.model_dump(mode="json", exclude_none=True)
    if payload.sort_order is not None:
        view.sort_order = payload.sort_order
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiProblem(
            status=409,
            code="SAVED_VIEW_NAME_CONFLICT",
            title="Saved account view already exists",
            detail="Another saved account view uses the requested name.",
        ) from exc
    await session.refresh(view)
    return view


async def delete_saved_account_view(session: AsyncSession, view_id: uuid.UUID) -> None:
    view = await get_saved_account_view_or_404(session, view_id)
    await session.delete(view)
    await session.commit()


async def resolve_account_view_filters(
    session: AsyncSession,
    *,
    builtin_key: str | None,
    saved_view_id: uuid.UUID | None,
) -> AccountViewFilters | None:
    if builtin_key and saved_view_id:
        raise ApiProblem(
            status=400,
            code="ACCOUNT_VIEW_AMBIGUOUS",
            title="Account view is ambiguous",
            detail="Choose either a built-in view or a saved view, not both.",
        )
    if builtin_key:
        view = next((item for item in builtin_account_views() if item.key == builtin_key), None)
        if not view:
            raise ApiProblem(
                status=404,
                code="BUILTIN_VIEW_NOT_FOUND",
                title="Built-in account view not found",
                detail=f"No built-in account view uses key {builtin_key!r}.",
            )
        return view.filters
    if saved_view_id:
        saved = await get_saved_account_view_or_404(session, saved_view_id)
        return AccountViewFilters.model_validate(saved.filters)
    return None
