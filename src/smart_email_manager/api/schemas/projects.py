from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)
    default_lease_seconds: int = Field(default=300, ge=30, le=3600)
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20_000)


class ProjectStatusWrite(BaseModel):
    status: Literal["active", "paused", "completed"]


class ProjectAccountsAdd(BaseModel):
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=20_000)


class ProjectAccountsAction(BaseModel):
    action: Literal["reset_failed", "remove", "restore"]
    project_account_ids: list[uuid.UUID] = Field(min_length=1, max_length=20_000)


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    status: str
    default_lease_seconds: int
    total_count: int
    to_claim_count: int
    leased_count: int
    done_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime


class ProjectAccountsActionResult(BaseModel):
    requested_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    project: ProjectRead


class ProjectAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    account_id: uuid.UUID
    email: str
    status: str
    lease_owner: str | None
    lease_expires_at: datetime | None
    attempt_count: int
    result: dict[str, object]
    error_summary: str | None
    finished_at: datetime | None


class ProjectClaimRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=160)
    lease_seconds: int | None = Field(default=None, ge=30, le=3600)


class ProjectClaimRead(BaseModel):
    project_account_id: uuid.UUID
    project_id: uuid.UUID
    account_id: uuid.UUID
    email: str
    claim_token: str
    lease_owner: str
    lease_expires_at: datetime
    attempt_count: int


class ProjectLeaseAction(BaseModel):
    claim_token: SecretStr
    result: dict[str, object] = Field(default_factory=dict)
    error_summary: str | None = Field(default=None, max_length=2_000)


class ProjectLeaseHeartbeat(BaseModel):
    claim_token: SecretStr
    lease_seconds: int | None = Field(default=None, ge=30, le=3600)


class ProjectEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    project_id: uuid.UUID
    project_account_id: uuid.UUID | None
    event_type: str
    actor: str | None
    data: dict[str, object]
    created_at: datetime
