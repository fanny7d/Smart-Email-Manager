from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ImportBatchCreate(BaseModel):
    content: SecretStr
    account_type: Literal["outlook"] = "outlook"
    provider: str = Field(default="outlook", min_length=1, max_length=32)
    group_id: uuid.UUID | None = None
    remark: str = Field(default="", max_length=2_000)


class ImportBatchItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    status: str
    email: str | None
    account_type: str
    provider: str
    group_id: uuid.UUID | None
    remark: str
    provider_metadata: dict[str, object]
    error_code: str | None
    error_message: str | None
    created_account_id: uuid.UUID | None


class ImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    account_type: str
    provider: str
    group_id: uuid.UUID | None
    remark: str
    total_count: int
    valid_count: int
    invalid_count: int
    conflict_count: int
    created_count: int
    skipped_count: int
    failed_count: int
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ImportBatchDetail(ImportBatchRead):
    items: list[ImportBatchItemRead]
