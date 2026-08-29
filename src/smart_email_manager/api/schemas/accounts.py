from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator


class AccountCreate(BaseModel):
    email: EmailStr
    account_type: Literal["outlook"] = "outlook"
    provider: Literal["outlook"] = "outlook"
    group_id: uuid.UUID | None = None
    remark: str = Field(default="", max_length=2_000)


class AccountListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    account_type: str
    provider: str
    authorization_type: str
    lifecycle_status: str
    authorization_status: str
    token_status: str
    mail_health_status: str
    proxy_health_status: str
    group_id: uuid.UUID | None
    remark: str
    last_token_check_at: datetime | None
    last_mail_check_at: datetime | None
    last_mail_success_at: datetime | None
    last_message_at: datetime | None
    health_reason_code: str | None
    health_error_summary: str | None
    consecutive_failures: int
    row_version: int
    created_at: datetime
    updated_at: datetime


class AccountPage(BaseModel):
    items: list[AccountListItem]
    next_cursor: str | None = None
    limit: int = Field(ge=1, le=500)


class AccountUpdate(BaseModel):
    row_version: int = Field(ge=1)
    email: EmailStr | None = None
    account_type: Literal["outlook"] | None = None
    provider: Literal["outlook"] | None = None
    authorization_type: str | None = Field(default=None, max_length=32)
    lifecycle_status: Literal["active", "inactive", "archived"] | None = None
    group_id: uuid.UUID | None = None
    remark: str | None = Field(default=None, max_length=2_000)
    provider_metadata: dict[str, object] | None = None


class AccountBulkChanges(BaseModel):
    lifecycle_status: Literal["active", "inactive", "archived"] | None = None
    move_group: bool = False
    group_id: uuid.UUID | None = None
    add_tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    remove_tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    forwarding_enabled: bool | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> AccountBulkChanges:
        if not any(
            (
                self.lifecycle_status is not None,
                self.move_group,
                self.add_tag_ids,
                self.remove_tag_ids,
                self.forwarding_enabled is not None,
            )
        ):
            raise ValueError("at least one bulk change is required")
        return self


class AccountBulkMutation(AccountBulkChanges):
    account_ids: list[uuid.UUID] = Field(min_length=1, max_length=20_000)


class AccountBulkSelection(BaseModel):
    scope: Literal["ids", "filter"]
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20_000)
    lifecycle_status: Literal["active", "inactive", "archived"] | None = None
    token_status: Literal["never", "checking", "success", "failed", "stale"] | None = None
    mail_health_status: Literal["unknown", "checking", "healthy", "degraded", "failed"] | None = None
    query: str | None = Field(default=None, max_length=320)
    view: str | None = Field(default=None, max_length=64)
    saved_view_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def scope_matches_payload(self) -> AccountBulkSelection:
        if self.scope == "ids" and not self.account_ids:
            raise ValueError("ids scope requires account_ids")
        if self.scope == "filter" and self.account_ids:
            raise ValueError("filter scope cannot include account_ids")
        return self


class AccountBulkPreviewCreate(BaseModel):
    selection: AccountBulkSelection
    changes: AccountBulkChanges


class AccountBulkPreviewRead(BaseModel):
    preview_token: str
    scope: str
    matched_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    dangerous_count: int = Field(ge=0)
    expires_at: datetime


class AccountBulkExecute(BaseModel):
    preview_token: SecretStr


class AccountBulkResult(BaseModel):
    requested_count: int
    matched_count: int
    updated_count: int
    not_found_ids: list[uuid.UUID]


class AccountArchiveRequest(BaseModel):
    row_version: int = Field(ge=1)
