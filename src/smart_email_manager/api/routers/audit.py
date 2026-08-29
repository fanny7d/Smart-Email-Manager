from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.audit import AuditLogRead
from smart_email_manager.services.audit import list_audit_logs

router = APIRouter(prefix="/audit-logs", tags=["audit"])
AuditRead = Annotated[object, Depends(require_scopes("audit:read"))]


@router.get("", operation_id="list_audit_logs", response_model=list[AuditLogRead])
async def get_audit_logs(
    session: SessionDependency,
    _auth: AuditRead,
    resource_type: str | None = None,
    resource_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[AuditLogRead]:
    return [
        AuditLogRead.model_validate(row)
        for row in await list_audit_logs(
            session,
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
        )
    ]
