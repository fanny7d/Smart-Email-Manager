from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from smart_email_manager.api.schemas.fleet import FleetSummary, StatusCount
from smart_email_manager.db.models import Account
from smart_email_manager.domain.enums import LifecycleStatus


async def _status_counts(
    session: AsyncSession,
    column: InstrumentedAttribute[str],
) -> list[StatusCount]:
    rows = (await session.execute(select(column, func.count()).group_by(column).order_by(column))).all()
    return [StatusCount(status=str(status), count=count) for status, count in rows]


async def get_fleet_summary(session: AsyncSession) -> FleetSummary:
    total_accounts = await session.scalar(select(func.count()).select_from(Account)) or 0
    active_accounts = (
        await session.scalar(
            select(func.count())
            .select_from(Account)
            .where(Account.lifecycle_status == LifecycleStatus.ACTIVE)
        )
        or 0
    )
    needs_attention = (
        await session.scalar(
            select(func.count())
            .select_from(Account)
            .where(
                or_(
                    Account.authorization_status.in_(
                        ("unknown", "pending", "invalid", "reauthorization_required")
                    ),
                    Account.token_status.in_(("never", "failed", "stale")),
                    Account.mail_health_status.in_(("degraded", "failed")),
                    Account.proxy_health_status == "failed",
                )
            )
        )
        or 0
    )

    return FleetSummary(
        total_accounts=total_accounts,
        active_accounts=active_accounts,
        needs_attention=needs_attention,
        lifecycle=await _status_counts(session, Account.lifecycle_status),
        authorization=await _status_counts(session, Account.authorization_status),
        token=await _status_counts(session, Account.token_status),
        mail_health=await _status_counts(session, Account.mail_health_status),
        proxy_health=await _status_counts(session, Account.proxy_health_status),
    )
