from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _default_folders() -> list[Literal["inbox", "junkemail"]]:
    return ["inbox"]


class EmailShareCreate(BaseModel):
    account_id: uuid.UUID
    duration_minutes: int = Field(default=1440, ge=1, le=2_628_000)
    never_expires: bool = False
    allowed_folders: list[Literal["inbox", "junkemail"]] = Field(
        default_factory=_default_folders, min_length=1, max_length=2
    )


class EmailShareRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    token_prefix: str
    allowed_folders: list[str]
    expires_at: datetime | None
    never_expires: bool
    revoked_at: datetime | None
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    status: str


class EmailShareCreated(EmailShareRead):
    token: str
    share_path: str


class PublicEmailShareStatus(BaseModel):
    status: str
    account_id: uuid.UUID
    email: str
    allowed_folders: list[str]
    expires_at: datetime | None
