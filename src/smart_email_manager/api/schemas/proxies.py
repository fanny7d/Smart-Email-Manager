from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ProxyProfileWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    primary_url: SecretStr
    fallback_url_1: SecretStr | None = None
    fallback_url_2: SecretStr | None = None
    enabled: bool = True


class ProxyProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    enabled: bool
    primary_hint: str
    fallback_hint_1: str | None
    fallback_hint_2: str | None
    key_version: int
    health_status: str
    health_reason_code: str | None
    last_tested_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProxyAssignment(BaseModel):
    proxy_profile_id: uuid.UUID | None = None


class ResolvedProxyRead(BaseModel):
    account_id: uuid.UUID
    source: Literal["account", "group", "none"]
    source_group_id: uuid.UUID | None = None
    proxy_profile_id: uuid.UUID | None = None
    profile_name: str | None = None
    endpoint_hints: list[str] = Field(default_factory=list)


class ProxyProbeAttemptRead(BaseModel):
    endpoint_hint: str
    success: bool
    reason_code: str
    latency_ms: int
    message: str = ""


class ProxyProbeRead(BaseModel):
    profile_id: uuid.UUID
    status: str
    reason_code: str
    attempts: list[ProxyProbeAttemptRead]
    tested_at: datetime
