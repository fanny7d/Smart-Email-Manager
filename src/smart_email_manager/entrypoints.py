from __future__ import annotations

import asyncio
import logging

import uvicorn

from smart_email_manager.config import get_settings
from smart_email_manager.jobs.worker import run_forever


def run_api() -> None:
    settings = get_settings()
    uvicorn.run(
        "smart_email_manager.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    try:
        asyncio.run(run_forever(settings))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("worker stopped")
