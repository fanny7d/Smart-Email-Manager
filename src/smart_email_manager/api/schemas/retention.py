from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _default_folders() -> list[Literal["inbox", "junkemail"]]:
    return ["inbox"]


class RetentionPolicyWrite(BaseModel):
    enabled: bool = True
    retain_bodies: bool = False
    folders: list[Literal["inbox", "junkemail"]] = Field(
        default_factory=_default_folders, min_length=1, max_length=2
    )
    max_messages: int = Field(default=1000, ge=1, le=100_000)
    max_age_days: int = Field(default=30, ge=1, le=3650)


class RetentionPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    enabled: bool
    retain_bodies: bool
    folders: list[str]
    max_messages: int
    max_age_days: int
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RetentionSyncJobCreate(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    limit: int = Field(default=500, ge=1, le=5000)


class RetentionStatsRead(BaseModel):
    account_count: int
    message_count: int
    body_count: int
    estimated_bytes: int
