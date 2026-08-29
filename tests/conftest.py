from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import text

os.environ["SEM_ENVIRONMENT"] = "test"
os.environ["SEM_DATABASE_URL"] = os.getenv(
    "SEM_TEST_DATABASE_URL",
    os.getenv("SEM_DATABASE_URL", "postgresql+psycopg:///smart_email_manager_test"),
)
os.environ["SEM_API_TOKEN"] = ""
os.environ["SEM_MASTER_KEY"] = base64.urlsafe_b64encode(b"test-master-key-material-32-byte").decode()
os.environ["SEM_MASTER_KEY_VERSION"] = "1"

from smart_email_manager.api.app import app  # noqa: E402
from smart_email_manager.config import get_settings  # noqa: E402
from smart_email_manager.db.session import (  # noqa: E402
    dispose_engine,
    get_engine,
)


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    get_settings.cache_clear()
    async with get_engine().begin() as connection:
        await connection.execute(
            text(
                """
                TRUNCATE TABLE
                    account_bulk_previews,
                    saved_account_views,
                    import_batch_items,
                    import_batches,
                    audit_logs,
                    project_events,
                    project_accounts,
                    work_projects,
                    forwarding_deliveries,
                    account_forwarding_destinations,
                    account_forwarding,
                    forwarding_destinations,
                    retained_mail_messages,
                    retention_policies,
                    email_share_links,
                    token_refresh_logs,
                    schedules,
                    job_events,
                    job_items,
                    jobs,
                    account_health_snapshots,
                    account_tags,
                    account_aliases,
                    account_secrets,
                    accounts,
                    tags,
                    groups,
                    proxy_profiles,
                    api_tokens
                RESTART IDENTITY CASCADE
                """
            )
        )
        await connection.execute(
            text(
                """
                INSERT INTO groups (id, name, description, color, sort_order, level, system_key)
                VALUES
                    (uuidv7(), '默认分组', 'Default Outlook group', '#64748b', 1, 1, 'default')
                """
            )
        )
    yield


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(scope="session", autouse=True)
async def close_database_engine() -> AsyncIterator[None]:
    yield
    await dispose_engine()
