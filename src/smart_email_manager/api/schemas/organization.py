from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    color: str = Field(default="#64748b", pattern=r"^#[0-9A-Fa-f]{6}$")
    parent_id: uuid.UUID | None = None


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    color: str
    sort_order: int
    level: int
    parent_id: uuid.UUID | None
    system_key: str | None
    direct_account_count: int = 0
    descendant_account_count: int = 0
    created_at: datetime
    updated_at: datetime


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#64748b", pattern=r"^#[0-9A-Fa-f]{6}$")


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str
    created_at: datetime
    updated_at: datetime


class AccountTagMutation(BaseModel):
    action: Literal["add", "remove", "replace"]
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class AliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime


class AliasesReplace(BaseModel):
    aliases: list[EmailStr] = Field(default_factory=list, max_length=500)
