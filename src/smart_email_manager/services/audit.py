from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smart_email_manager.db.models import AuditLog


def add_audit_log(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    data: dict[str, Any] | None = None,
    actor: str = "api",
) -> None:
    session.add(
        AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor=actor,
            data=data or {},
        )
    )


async def list_audit_logs(
    session: AsyncSession,
    *,
    resource_type: str | None,
    resource_id: str | None,
    limit: int,
) -> list[AuditLog]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if resource_type:
        statement = statement.where(AuditLog.resource_type == resource_type)
    if resource_id:
        statement = statement.where(AuditLog.resource_id == resource_id)
    return list((await session.scalars(statement)).all())
