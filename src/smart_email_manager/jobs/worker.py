from __future__ import annotations

import asyncio
import logging

from smart_email_manager.config import Settings, get_settings
from smart_email_manager.db.session import get_session_factory
from smart_email_manager.domain.enums import JobItemStatus
from smart_email_manager.jobs.handlers import HANDLERS
from smart_email_manager.jobs.queue import (
    cancel_pending_items,
    finish_item,
    lease_next_item,
    recover_expired_leases,
    retry_item,
)
from smart_email_manager.services.jobs import finalize_pausing_jobs
from smart_email_manager.services.schedules import run_due_schedules

logger = logging.getLogger(__name__)


async def run_once(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        await run_due_schedules(session)
        await recover_expired_leases(session)
        await cancel_pending_items(session)
        await finalize_pausing_jobs(session)
        lease = await lease_next_item(
            session,
            worker_id=settings.worker_id,
            lease_seconds=settings.job_lease_seconds,
        )
    if lease is None:
        return False

    handler = HANDLERS.get(lease.job_type)
    async with session_factory() as session:
        if handler is None:
            await finish_item(
                session,
                lease,
                status=JobItemStatus.FAILED,
                error_code="UNKNOWN_JOB_TYPE",
                error_summary=f"No worker handler is registered for {lease.job_type}.",
            )
            return True
        try:
            await handler(session, lease)
        except Exception as exc:
            await session.rollback()
            async with session_factory() as failure_session:
                await retry_item(
                    failure_session,
                    lease,
                    error_code="UNHANDLED_JOB_ERROR",
                    error_summary=str(exc)[:500],
                )
            logger.exception("job item failed", extra={"job_id": str(lease.job_id), "item_id": str(lease.id)})
    return True


async def run_forever(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    logger.info("worker started", extra={"worker_id": settings.worker_id})
    while True:
        worked = await run_once(settings)
        if not worked:
            await asyncio.sleep(settings.worker_poll_seconds)
