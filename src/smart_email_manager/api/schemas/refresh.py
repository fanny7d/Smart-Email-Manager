from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TokenRefreshJobCreate(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    failed_only: bool = False
    limit: int = Field(default=500, ge=1, le=5_000)


class TokenRefreshLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    job_id: uuid.UUID | None
    status: str
    channel: str | None
    reason_code: str | None
    error_summary: str | None
    rotated: bool
    created_at: datetime


class TokenRefreshSummary(BaseModel):
    total_refreshable: int
    never: int
    success: int
    failed: int
    stale: int


class ScheduleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    task_type: Literal["token_refresh", "retention_sync", "forwarding"] = "token_refresh"
    cron_expression: str = Field(min_length=5, max_length=120)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    enabled: bool = True
    payload: dict[str, object] = Field(default_factory=dict)


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    task_type: str
    cron_expression: str
    timezone: str
    enabled: bool
    payload: dict[str, object]
    next_run_at: datetime
    last_run_at: datetime | None
    last_job_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
