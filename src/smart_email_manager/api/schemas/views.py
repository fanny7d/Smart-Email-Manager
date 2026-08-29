from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccountViewFilters(BaseModel):
    lifecycle_statuses: list[Literal["active", "inactive", "archived"]] = Field(
        default_factory=list, max_length=3
    )
    authorization_statuses: list[
        Literal["unknown", "pending", "valid", "invalid", "reauthorization_required"]
    ] = Field(default_factory=list, max_length=5)
    token_statuses: list[Literal["never", "checking", "success", "failed", "stale"]] = Field(
        default_factory=list, max_length=5
    )
    mail_health_statuses: list[Literal["unknown", "checking", "healthy", "degraded", "failed"]] = Field(
        default_factory=list, max_length=5
    )
    proxy_health_statuses: list[Literal["not_configured", "unknown", "healthy", "failed"]] = Field(
        default_factory=list, max_length=4
    )
    group_id: uuid.UUID | None = None
    ungrouped: bool = False
    untagged: bool = False
    min_consecutive_failures: int | None = Field(default=None, ge=1, le=1_000_000)
    last_mail_success_before: datetime | None = None
    query: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def group_filter_is_unambiguous(self) -> AccountViewFilters:
        if self.group_id is not None and self.ungrouped:
            raise ValueError("group_id and ungrouped cannot be combined")
        return self


class BuiltinAccountViewRead(BaseModel):
    key: str
    name: str
    description: str
    filters: AccountViewFilters


class SavedAccountViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: AccountViewFilters
    sort_order: int = Field(default=0, ge=-1_000_000, le=1_000_000)


class SavedAccountViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    filters: AccountViewFilters | None = None
    sort_order: int | None = Field(default=None, ge=-1_000_000, le=1_000_000)


class SavedAccountViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    filters: AccountViewFilters
    sort_order: int
    created_at: datetime
    updated_at: datetime


class AccountViewsRead(BaseModel):
    builtin: list[BuiltinAccountViewRead]
    saved: list[SavedAccountViewRead]
