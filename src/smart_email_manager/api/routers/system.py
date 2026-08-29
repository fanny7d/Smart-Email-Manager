from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from smart_email_manager import __version__
from smart_email_manager.api.dependencies import SessionDependency
from smart_email_manager.api.schemas.system import SystemHealth

router = APIRouter(prefix="/system", tags=["system"])


@router.get(
    "/health",
    operation_id="system_health",
    response_model=SystemHealth,
    summary="Check API and database health",
)
async def system_health(session: SessionDependency) -> SystemHealth:
    await session.execute(text("SELECT 1"))
    return SystemHealth(
        status="ok",
        database="ok",
        version=__version__,
        checked_at=datetime.now(UTC),
    )
