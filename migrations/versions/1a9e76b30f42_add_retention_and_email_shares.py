"""add retention and email shares

Revision ID: 1a9e76b30f42
Revises: 8b11c79c5e24
Create Date: 2026-08-28 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1a9e76b30f42"
down_revision: str | Sequence[str] | None = "8b11c79c5e24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_share_links",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("token_prefix", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "allowed_folders",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[\"inbox\"]'::jsonb"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("never_expires", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_email_share_links_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_share_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_share_links_token_hash")),
    )
    op.create_index(
        "ix_email_share_links_account_created",
        "email_share_links",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_email_share_links_status",
        "email_share_links",
        ["revoked_at", "expires_at", "never_expires"],
        unique=False,
    )
    op.create_table(
        "retention_policies",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("retain_bodies", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "folders",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[\"inbox\"]'::jsonb"),
            nullable=False,
        ),
        sa.Column("max_messages", sa.Integer(), server_default="1000", nullable=False),
        sa.Column("max_age_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_retention_policies_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_retention_policies")),
    )
    op.create_table(
        "retained_mail_messages",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("folder", sa.String(length=32), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("id_mode", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.Text(), server_default="", nullable=False),
        sa.Column("sender", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "recipients",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "cc",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("received_at", sa.String(length=80), server_default="", nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("has_attachments", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("body_preview", sa.Text(), server_default="", nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_type", sa.String(length=16), server_default="text", nullable=False),
        sa.Column(
            "attachments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("body_cached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_retained_mail_messages_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retained_mail_messages")),
        sa.UniqueConstraint(
            "account_id",
            "folder",
            "provider_message_id",
            "id_mode",
            name=op.f("uq_retained_mail_messages_account_id"),
        ),
    )
    op.create_index(
        "ix_retained_mail_account_folder_received",
        "retained_mail_messages",
        ["account_id", "folder", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retained_mail_account_folder_received",
        table_name="retained_mail_messages",
    )
    op.drop_table("retained_mail_messages")
    op.drop_table("retention_policies")
    op.drop_index("ix_email_share_links_status", table_name="email_share_links")
    op.drop_index("ix_email_share_links_account_created", table_name="email_share_links")
    op.drop_table("email_share_links")
