from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ForwardingDestinationWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel: Literal["smtp"]
    enabled: bool = True
    config: dict[str, str | int | bool] = Field(default_factory=dict)
    secret: SecretStr | None = None


class ForwardingDestinationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    channel: str
    enabled: bool
    config: dict[str, object]
    has_secret: bool
    key_version: int
    created_at: datetime
    updated_at: datetime


class AccountForwardingWrite(BaseModel):
    enabled: bool = True
    include_junk: bool = False
    window_minutes: int = Field(default=0, ge=0, le=10_080)
    destination_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class AccountForwardingRead(BaseModel):
    account_id: uuid.UUID
    enabled: bool
    include_junk: bool
    window_minutes: int
    cursor_at: datetime | None
    destination_ids: list[uuid.UUID]
    updated_at: datetime | None


class ForwardingJobCreate(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    limit: int = Field(default=500, ge=1, le=5000)


class ForwardingCursorWrite(BaseModel):
    cursor_at: datetime | None = None


class ForwardingDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    message_id: str
    folder: str
    destination_id: uuid.UUID
    channel: str
    status: str
    attempt_count: int
    error_code: str | None
    error_summary: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ForwardingTestResult(BaseModel):
    success: bool
    channel: str
    reason_code: str
    message: str = ""
