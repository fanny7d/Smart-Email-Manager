from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class VerificationCodeRead(BaseModel):
    account_id: uuid.UUID
    email: str
    code: str
    code_type: Literal["verification", "otp", "login", "security"]
    subject: str
    sender: str
    received_at: str
    folder: str
    message_id: str
    method: str
    confidence: Literal["high", "medium"]


class VerificationCodePage(BaseModel):
    items: list[VerificationCodeRead]
    checked_accounts: int
    failed_accounts: int = 0
    partial_errors: dict[str, str] = Field(default_factory=dict)


class VerificationCodeQuery(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    recent_minutes: int = Field(default=30, ge=1, le=1_440)
    messages_per_account: int = Field(default=30, ge=1, le=100)
    account_limit: int = Field(default=100, ge=1, le=500)
    include_junk: bool = True
    method: Literal["auto", "graph", "imap"] = "auto"
