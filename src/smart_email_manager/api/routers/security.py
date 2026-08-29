from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from smart_email_manager.api.dependencies import SessionDependency, require_scopes
from smart_email_manager.api.schemas.security import (
    MasterKeyRotationRequest,
    MasterKeyRotationResult,
)
from smart_email_manager.services.key_rotation import rotate_master_key

router = APIRouter(prefix="/security", tags=["security"])
SecurityRotate = Annotated[object, Depends(require_scopes("security:rotate"))]


@router.post(
    "/master-key-rotations",
    operation_id="rotate_master_key",
    response_model=MasterKeyRotationResult,
)
async def post_master_key_rotation(
    payload: MasterKeyRotationRequest,
    session: SessionDependency,
    _auth: SecurityRotate,
) -> MasterKeyRotationResult:
    return await rotate_master_key(session, payload)
