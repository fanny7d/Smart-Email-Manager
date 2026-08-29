from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateHealthCheckJob(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    limit: int = Field(default=100, ge=1, le=500)
    mode: Literal["metadata", "connectivity"] = "metadata"


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: str
    priority: int
    payload: dict[str, Any]
    result: dict[str, Any]
    total_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    cancel_requested_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    job_id: uuid.UUID
    job_item_id: uuid.UUID | None
    event_type: str
    level: str
    message: str
    data: dict[str, Any]
    created_at: datetime


class JobEventsPage(BaseModel):
    items: list[JobEventRead]
    next_sequence: int | None = None
