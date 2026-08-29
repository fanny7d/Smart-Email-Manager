from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.api.schemas.refresh import TokenRefreshSummary
from smart_email_manager.db.models import Account, AccountSecret, TokenRefreshLog
from smart_email_manager.domain.enums import LifecycleStatus, TokenStatus


async def list_token_refresh_logs(
    session: AsyncSession,
    *,
    account_id: uuid.UUID | None,
    limit: int,
) -> list[TokenRefreshLog]:
    statement = select(TokenRefreshLog).order_by(TokenRefreshLog.created_at.desc()).limit(limit)
    if account_id:
        statement = statement.where(TokenRefreshLog.account_id == account_id)
    return list((await session.scalars(statement)).all())


async def get_token_refresh_summary(session: AsyncSession) -> TokenRefreshSummary:
    refreshable = (
        select(Account.token_status)
        .join(AccountSecret, AccountSecret.account_id == Account.id)
        .where(
            Account.lifecycle_status == LifecycleStatus.ACTIVE,
            AccountSecret.refresh_token_ciphertext.is_not(None),
        )
        .subquery()
    )
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(refreshable.c.token_status == TokenStatus.NEVER),
                func.count().filter(refreshable.c.token_status == TokenStatus.SUCCESS),
                func.count().filter(refreshable.c.token_status == TokenStatus.FAILED),
                func.count().filter(refreshable.c.token_status == TokenStatus.STALE),
            ).select_from(refreshable)
        )
    ).one()
    total, never, success, failed, stale = (int(value or 0) for value in row)
    return TokenRefreshSummary(
        total_refreshable=total,
        never=never,
        success=success,
        failed=failed,
        stale=stale,
    )
