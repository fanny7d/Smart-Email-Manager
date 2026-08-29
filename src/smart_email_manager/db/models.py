from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from smart_email_manager.db.base import Base
from smart_email_manager.domain.enums import (
    AuthorizationStatus,
    JobItemStatus,
    JobStatus,
    LifecycleStatus,
    MailHealthStatus,
    ProxyHealthStatus,
    TokenStatus,
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )


class ProxyProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proxy_profiles"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    primary_url_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fallback_url_1_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    fallback_url_2_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"), nullable=False)
    health_status: Mapped[str] = mapped_column(
        String(32), default="unknown", server_default="unknown", nullable=False
    )
    health_reason_code: Mapped[str | None] = mapped_column(String(96))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Group(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 3", name="level_range"),
        Index("ix_groups_parent_sort", "parent_id", "sort_order"),
    )

    legacy_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#64748b", server_default="#64748b")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="RESTRICT")
    )
    system_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    proxy_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxy_profiles.id", ondelete="SET NULL")
    )

    parent: Mapped[Group | None] = relationship(remote_side="Group.id", back_populates="children")
    children: Mapped[list[Group]] = relationship(back_populates="parent")
    proxy_profile: Mapped[ProxyProfile | None] = relationship()


class SavedAccountView(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_account_views"
    __table_args__ = (Index("ix_saved_account_views_sort", "sort_order", "id"),)

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


class AccountBulkPreview(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "account_bulk_previews"
    __table_args__ = (Index("ix_account_bulk_previews_expiry", "expires_at", "consumed_at"),)

    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    selection: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    mutation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    account_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dangerous_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('active','inactive','archived')", name="lifecycle_status_values"
        ),
        CheckConstraint(
            "authorization_status IN ('unknown','pending','valid','invalid','reauthorization_required')",
            name="authorization_status_values",
        ),
        CheckConstraint(
            "token_status IN ('never','checking','success','failed','stale')", name="token_status_values"
        ),
        CheckConstraint(
            "mail_health_status IN ('unknown','checking','healthy','degraded','failed')",
            name="mail_health_status_values",
        ),
        CheckConstraint(
            "proxy_health_status IN ('not_configured','unknown','healthy','failed')",
            name="proxy_health_status_values",
        ),
        CheckConstraint("account_type = 'outlook'", name="account_type_outlook"),
        CheckConstraint("provider = 'outlook'", name="provider_outlook"),
        Index("ix_accounts_group_created", "group_id", "created_at"),
        Index("ix_accounts_health", "mail_health_status", "token_status"),
        Index("ix_accounts_lifecycle", "lifecycle_status"),
    )

    legacy_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), default="outlook", server_default="outlook")
    provider: Mapped[str] = mapped_column(String(32), default="outlook", server_default="outlook")
    authorization_type: Mapped[str] = mapped_column(String(32), default="", server_default="")
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default=LifecycleStatus.ACTIVE, server_default=LifecycleStatus.ACTIVE
    )
    authorization_status: Mapped[str] = mapped_column(
        String(32), default=AuthorizationStatus.UNKNOWN, server_default=AuthorizationStatus.UNKNOWN
    )
    token_status: Mapped[str] = mapped_column(
        String(32), default=TokenStatus.NEVER, server_default=TokenStatus.NEVER
    )
    mail_health_status: Mapped[str] = mapped_column(
        String(32), default=MailHealthStatus.UNKNOWN, server_default=MailHealthStatus.UNKNOWN
    )
    proxy_health_status: Mapped[str] = mapped_column(
        String(32),
        default=ProxyHealthStatus.NOT_CONFIGURED,
        server_default=ProxyHealthStatus.NOT_CONFIGURED,
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL")
    )
    proxy_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxy_profiles.id", ondelete="SET NULL")
    )
    remark: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    last_token_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_mail_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_mail_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_reason_code: Mapped[str | None] = mapped_column(String(96))
    health_error_summary: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    row_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )

    group: Mapped[Group | None] = relationship()
    proxy_profile: Mapped[ProxyProfile | None] = relationship()
    aliases: Mapped[list[AccountAlias]] = relationship(back_populates="account", cascade="all, delete-orphan")
    secret: Mapped[AccountSecret | None] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )


class AccountSecret(TimestampMixin, Base):
    __tablename__ = "account_secrets"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    password_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    account: Mapped[Account] = relationship(back_populates="secret")


class AccountAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "account_aliases"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)

    account: Mapped[Account] = relationship(back_populates="aliases")


class Tag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#64748b", server_default="#64748b")


class AccountTag(Base):
    __tablename__ = "account_tags"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AccountHealthSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "account_health_snapshots"
    __table_args__ = (Index("ix_health_snapshots_account_checked", "account_id", "checked_at"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(32), default="metadata", server_default="metadata")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(96))
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TokenRefreshLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "token_refresh_logs"
    __table_args__ = (
        CheckConstraint("status IN ('success','failed','skipped')", name="status_values"),
        Index("ix_token_refresh_logs_account_created", "account_id", "created_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(96))
    error_summary: Mapped[str | None] = mapped_column(Text)
    rotated: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RetentionPolicy(TimestampMixin, Base):
    __tablename__ = "retention_policies"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    retain_bodies: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    folders: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: ["inbox"],
        server_default=text("'[\"inbox\"]'::jsonb"),
        nullable=False,
    )
    max_messages: Mapped[int] = mapped_column(Integer, default=1000, server_default="1000")
    max_age_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetainedMailMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "retained_mail_messages"
    __table_args__ = (
        UniqueConstraint("account_id", "folder", "provider_message_id", "id_mode"),
        Index("ix_retained_mail_account_folder_received", "account_id", "folder", "received_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    folder: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    id_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    sender: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    recipients: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    cc: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    received_at: Mapped[str] = mapped_column(String(80), default="", server_default="", nullable=False)
    is_read: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    has_attachments: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    body_preview: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    body_type: Mapped[str] = mapped_column(String(16), default="text", server_default="text")
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    body_cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmailShareLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_share_links"
    __table_args__ = (
        Index("ix_email_share_links_account_created", "account_id", "created_at"),
        Index("ix_email_share_links_status", "revoked_at", "expires_at", "never_expires"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    allowed_folders: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: ["inbox"],
        server_default=text("'[\"inbox\"]'::jsonb"),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    never_expires: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ForwardingDestination(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forwarding_destinations"
    __table_args__ = (CheckConstraint("channel = 'smtp'", name="channel_values"),)

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class AccountForwarding(TimestampMixin, Base):
    __tablename__ = "account_forwarding"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    include_junk: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cursor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountForwardingDestination(Base):
    __tablename__ = "account_forwarding_destinations"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_forwarding.account_id", ondelete="CASCADE"), primary_key=True
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("forwarding_destinations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ForwardingDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forwarding_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('processing','success','failed')", name="status_values"),
        UniqueConstraint("account_id", "message_id", "destination_id"),
        Index("ix_forwarding_deliveries_account_created", "account_id", "created_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    folder: Mapped[str] = mapped_column(String(32), nullable=False)
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("forwarding_destinations.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(96))
    error_summary: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_projects"
    __table_args__ = (CheckConstraint("status IN ('active','paused','completed')", name="status_values"),)

    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active")
    default_lease_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="300")


class ProjectAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('to_claim','leased','done','failed','removed')",
            name="status_values",
        ),
        UniqueConstraint("project_id", "account_id"),
        Index("ix_project_accounts_claim", "project_id", "status", "lease_expires_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_projects.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="to_claim", server_default="to_claim")
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_token_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectEvent(Base):
    __tablename__ = "project_events"

    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_projects.id", ondelete="CASCADE"), nullable=False
    )
    project_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_accounts.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(160))
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_resource_created", "resource_type", "resource_id", "created_at"),)

    action: Mapped[str] = mapped_column(String(96), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(320))
    actor: Mapped[str] = mapped_column(String(160), default="api", server_default="api")
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Schedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('token_refresh','retention_sync','forwarding')",
            name="task_type_values",
        ),
        Index("ix_schedules_due", "enabled", "next_run_at"),
    )

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Shanghai", server_default="Asia/Shanghai")
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','pausing','paused','cancelling',"
            "'cancelled','completed','partial','failed')",
            name="status_values",
        ),
        Index("ix_jobs_status_priority", "status", "priority", "created_at"),
    )

    job_type: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED, server_default=JobStatus.QUEUED)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    total_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[JobItem]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','leased','running','retry_wait','succeeded',"
            "'failed','skipped','cancelled')",
            name="status_values",
        ),
        UniqueConstraint("job_id", "item_key"),
        Index("ix_job_items_lease", "status", "run_after", "lease_expires_at"),
        Index("ix_job_items_job_status", "job_id", "status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    item_key: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(
        String(32), default=JobItemStatus.PENDING, server_default=JobItemStatus.PENDING
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(96))
    error_summary: Mapped[str | None] = mapped_column(Text)

    job: Mapped[Job] = relationship(back_populates="items")


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_sequence", "job_id", "sequence"),)

    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    job_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_items.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="info", server_default="info")
    message: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_tokens"
    __table_args__ = (Index("ix_api_tokens_prefix", "token_prefix"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint("account_type = 'outlook'", name="account_type_outlook"),
        CheckConstraint(
            "status IN ('validated','committing','completed','partial','failed','rolled_back')",
            name="status_values",
        ),
        Index("ix_import_batches_status_created", "status", "created_at"),
    )

    status: Mapped[str] = mapped_column(String(32), default="validated", server_default="validated")
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL")
    )
    remark: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    invalid_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[ImportBatchItem]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ImportBatchItem.line_number",
    )


class ImportBatchItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_batch_items"
    __table_args__ = (
        CheckConstraint("account_type = 'outlook'", name="account_type_outlook"),
        CheckConstraint(
            "status IN ('valid','invalid','conflict','created','skipped','failed','rolled_back')",
            name="status_values",
        ),
        UniqueConstraint("batch_id", "line_number"),
        Index("ix_import_batch_items_batch_status", "batch_id", "status"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    email_normalized: Mapped[str | None] = mapped_column(String(320))
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL")
    )
    remark: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False
    )
    password_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_version: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(96))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )

    batch: Mapped[ImportBatch] = relationship(back_populates="items")
