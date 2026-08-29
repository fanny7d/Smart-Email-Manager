"""reduce product scope to Outlook mailbox management

Revision ID: 0d4e5f6a7b8c
Revises: f6b7c8d9e0a1
Create Date: 2026-08-29 10:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0d4e5f6a7b8c"
down_revision: str | None = "f6b7c8d9e0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _require_removed_features_empty() -> None:
    connection = op.get_bind()
    for table in (
        "backup_runs",
        "webdav_backup_profiles",
        "temp_mail_messages",
        "temp_mailboxes",
        "temp_mail_channels",
    ):
        count = connection.scalar(sa.text(f"SELECT count(*) FROM {table}"))
        if count:
            raise RuntimeError(f"Refusing to remove non-empty out-of-scope table: {table}")


def upgrade() -> None:
    _require_removed_features_empty()

    op.drop_table("backup_runs")
    op.drop_table("webdav_backup_profiles")
    op.drop_table("temp_mail_messages")
    op.drop_table("temp_mailboxes")
    op.drop_table("temp_mail_channels")

    op.drop_column("account_secrets", "imap_password_ciphertext")
    op.drop_column("import_batch_items", "imap_password_ciphertext")

    op.drop_constraint(
        op.f("ck_forwarding_destinations_channel_values"),
        "forwarding_destinations",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_forwarding_destinations_channel_values"),
        "forwarding_destinations",
        "channel = 'smtp'",
    )
    op.drop_constraint(op.f("ck_schedules_task_type_values"), "schedules", type_="check")
    op.create_check_constraint(
        op.f("ck_schedules_task_type_values"),
        "schedules",
        "task_type IN ('token_refresh','retention_sync','forwarding')",
    )
    op.create_check_constraint(
        op.f("ck_accounts_account_type_outlook"), "accounts", "account_type = 'outlook'"
    )
    op.create_check_constraint(
        op.f("ck_accounts_provider_outlook"), "accounts", "provider = 'outlook'"
    )
    op.create_check_constraint(
        op.f("ck_import_batches_account_type_outlook"),
        "import_batches",
        "account_type = 'outlook'",
    )
    op.create_check_constraint(
        op.f("ck_import_batch_items_account_type_outlook"),
        "import_batch_items",
        "account_type = 'outlook'",
    )
    op.execute(
        "DELETE FROM groups WHERE system_key = 'temporary' "
        "AND NOT EXISTS (SELECT 1 FROM accounts WHERE accounts.group_id = groups.id)"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_import_batch_items_account_type_outlook"),
        "import_batch_items",
        type_="check",
    )
    op.drop_constraint(op.f("ck_import_batches_account_type_outlook"), "import_batches", type_="check")
    op.drop_constraint(op.f("ck_accounts_provider_outlook"), "accounts", type_="check")
    op.drop_constraint(op.f("ck_accounts_account_type_outlook"), "accounts", type_="check")

    op.drop_constraint(op.f("ck_schedules_task_type_values"), "schedules", type_="check")
    op.create_check_constraint(
        op.f("ck_schedules_task_type_values"),
        "schedules",
        "task_type IN ('token_refresh','retention_sync','forwarding','webdav_backup')",
    )
    op.drop_constraint(
        op.f("ck_forwarding_destinations_channel_values"),
        "forwarding_destinations",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_forwarding_destinations_channel_values"),
        "forwarding_destinations",
        "channel IN ('smtp','telegram','wecom')",
    )

    op.add_column("account_secrets", sa.Column("imap_password_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column(
        "import_batch_items",
        sa.Column("imap_password_ciphertext", sa.LargeBinary(), nullable=True),
    )

    op.create_table(
        "webdav_backup_profiles",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("connection_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("remote_prefix", sa.String(240), server_default="", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webdav_backup_profiles")),
        sa.UniqueConstraint("name", name=op.f("uq_webdav_backup_profiles_name")),
    )
    op.create_table(
        "backup_runs",
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("remote_path", sa.String(500), server_default="", nullable=False),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("size_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_summary", sa.Text()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["profile_id"], ["webdav_backup_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_runs")),
    )

    op.create_table(
        "temp_mail_channels",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("domains", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temp_mail_channels")),
        sa.UniqueConstraint("name", name=op.f("uq_temp_mail_channels_name")),
    )
    op.create_table(
        "temp_mailboxes",
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("address_normalized", sa.String(320), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(240)),
        sa.Column("access_ciphertext", sa.LargeBinary()),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["temp_mail_channels.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temp_mailboxes")),
        sa.UniqueConstraint("address_normalized", name=op.f("uq_temp_mailboxes_address_normalized")),
    )
    op.create_table(
        "temp_mail_messages",
        sa.Column("mailbox_id", sa.UUID(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), server_default="", nullable=False),
        sa.Column("recipients", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("subject", sa.Text(), server_default="", nullable=False),
        sa.Column("received_at", sa.String(80), server_default="", nullable=False),
        sa.Column("body_preview", sa.Text(), server_default="", nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("body_type", sa.String(16), server_default="text", nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["mailbox_id"], ["temp_mailboxes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_temp_mail_messages")),
        sa.UniqueConstraint(
            "mailbox_id",
            "provider_message_id",
            name=op.f("uq_temp_mail_messages_mailbox_id"),
        ),
    )
