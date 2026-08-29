"""add temp mail channels

Revision ID: a8c0e15d7f33
Revises: 9b27e6f43c81
Create Date: 2026-08-29 00:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8c0e15d7f33"
down_revision: str | Sequence[str] | None = "9b27e6f43c81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "temp_mail_channels",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column(
            "domains",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "provider IN ('gptmail','duckmail','cloudflare')",
            name=op.f("ck_temp_mail_channels_provider_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temp_mail_channels")),
        sa.UniqueConstraint("name", name=op.f("uq_temp_mail_channels_name")),
    )
    op.create_index(
        "uq_temp_mail_channels_default_provider",
        "temp_mail_channels",
        ["provider"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "temp_mailboxes",
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("address", sa.String(length=320), nullable=False),
        sa.Column("address_normalized", sa.String(length=320), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=240), nullable=True),
        sa.Column("access_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["temp_mail_channels.id"],
            name=op.f("fk_temp_mailboxes_channel_id_temp_mail_channels"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temp_mailboxes")),
        sa.UniqueConstraint("address_normalized", name=op.f("uq_temp_mailboxes_address_normalized")),
    )
    op.create_table(
        "temp_mail_messages",
        sa.Column("mailbox_id", sa.UUID(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "recipients",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("subject", sa.Text(), server_default="", nullable=False),
        sa.Column("received_at", sa.String(length=80), server_default="", nullable=False),
        sa.Column("body_preview", sa.Text(), server_default="", nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_type", sa.String(length=16), server_default="text", nullable=False),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["mailbox_id"],
            ["temp_mailboxes.id"],
            name=op.f("fk_temp_mail_messages_mailbox_id_temp_mailboxes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temp_mail_messages")),
        sa.UniqueConstraint(
            "mailbox_id",
            "provider_message_id",
            name=op.f("uq_temp_mail_messages_mailbox_id"),
        ),
    )
    op.create_index(
        "ix_temp_mail_messages_mailbox_received",
        "temp_mail_messages",
        ["mailbox_id", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_temp_mail_messages_mailbox_received", table_name="temp_mail_messages")
    op.drop_table("temp_mail_messages")
    op.drop_table("temp_mailboxes")
    op.drop_index("uq_temp_mail_channels_default_provider", table_name="temp_mail_channels")
    op.drop_table("temp_mail_channels")
