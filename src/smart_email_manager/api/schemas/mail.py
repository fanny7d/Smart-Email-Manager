from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MailAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    content_type: str
    size: int
    is_inline: bool


class MailSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    folder: str
    subject: str
    sender: str
    recipients: list[str]
    received_at: str
    is_read: bool
    has_attachments: bool
    body_preview: str
    id_mode: str


class MailPageRead(BaseModel):
    items: list[MailSummaryRead]
    has_more: bool
    method: str
    partial_errors: dict[str, object] = Field(default_factory=dict)


class MailDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    folder: str
    subject: str
    sender: str
    recipients: list[str]
    cc: list[str]
    received_at: str
    is_read: bool
    body: str
    body_type: str
    attachments: list[MailAttachmentRead]
    id_mode: str
    method: str
