from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from smart_email_manager.api.schemas.views import AccountViewFilters
from smart_email_manager.db.models import Account
from smart_email_manager.services.accounts import list_accounts
from smart_email_manager.services.fleet import get_fleet_summary


async def benchmark(database_url: str, account_count: int) -> dict[str, Any]:
    if account_count < 10_000:
        raise ValueError("scale acceptance requires at least 10,000 synthetic accounts")
    database_name = database_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database_name.endswith("_test"):
        raise ValueError("benchmark database name must end with _test")

    engine = create_async_engine(database_url)
    prefix = f"scale-{uuid.uuid4().hex[:12]}"
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            before_count = int(await session.scalar(select(func.count()).select_from(Account)) or 0)
            insert_started = time.perf_counter()
            await session.execute(
                text(
                    """
                    INSERT INTO accounts (
                        email,
                        email_normalized,
                        account_type,
                        provider,
                        lifecycle_status,
                        authorization_status,
                        token_status,
                        mail_health_status,
                        proxy_health_status,
                        consecutive_failures
                    )
                    SELECT
                        :prefix || '-' || value || '@example.test',
                        :prefix || '-' || value || '@example.test',
                        'outlook',
                        'outlook',
                        CASE WHEN value % 19 = 0 THEN 'inactive' ELSE 'active' END,
                        CASE WHEN value % 11 = 0 THEN 'reauthorization_required' ELSE 'valid' END,
                        CASE WHEN value % 7 = 0 THEN 'failed' ELSE 'success' END,
                        CASE WHEN value % 5 = 0 THEN 'failed' ELSE 'healthy' END,
                        CASE WHEN value % 23 = 0 THEN 'failed' ELSE 'not_configured' END,
                        CASE WHEN value % 5 = 0 THEN 3 ELSE 0 END
                    FROM generate_series(1, :account_count) AS value
                    """
                ),
                {"prefix": prefix, "account_count": account_count},
            )
            await session.flush()
            insert_seconds = time.perf_counter() - insert_started

            summary_started = time.perf_counter()
            summary = await get_fleet_summary(session)
            summary_seconds = time.perf_counter() - summary_started

            page_started = time.perf_counter()
            page, next_cursor = await list_accounts(session, limit=100)
            page_seconds = time.perf_counter() - page_started

            smart_view_started = time.perf_counter()
            failed_page, _failed_cursor = await list_accounts(
                session,
                limit=100,
                view_filters=AccountViewFilters(
                    mail_health_statuses=["failed"],
                    min_consecutive_failures=2,
                ),
            )
            smart_view_seconds = time.perf_counter() - smart_view_started

            after_count = int(await session.scalar(select(func.count()).select_from(Account)) or 0)
            if after_count - before_count != account_count:
                raise RuntimeError("synthetic account count does not match the requested scale")
            if len(page) != 100 or not next_cursor:
                raise RuntimeError("cursor pagination did not retain the 100-row rendering boundary")
            if not failed_page:
                raise RuntimeError("smart-view benchmark returned no seeded failures")

            return {
                "synthetic_accounts": account_count,
                "database_total_during_test": summary.total_accounts,
                "first_page_rows": len(page),
                "next_cursor_present": bool(next_cursor),
                "smart_view_page_rows": len(failed_page),
                "frontend_max_account_rows": 100,
                "timings_seconds": {
                    "insert": round(insert_seconds, 4),
                    "fleet_summary": round(summary_seconds, 4),
                    "first_cursor_page": round(page_seconds, 4),
                    "smart_view_page": round(smart_view_seconds, 4),
                },
                "rolled_back": True,
            }
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 10,000-account PostgreSQL scale gate")
    parser.add_argument(
        "--database-url",
        default=(
            os.getenv("SEM_TEST_DATABASE_URL")
            or os.getenv("SEM_DATABASE_URL")
            or "postgresql+psycopg:///smart_email_manager_test"
        ),
    )
    parser.add_argument("--accounts", type=int, default=10_000)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(benchmark(args.database_url, args.accounts)), indent=2))


if __name__ == "__main__":
    main()
