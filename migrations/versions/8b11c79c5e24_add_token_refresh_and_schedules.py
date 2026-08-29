"""add token refresh and schedules

Revision ID: 8b11c79c5e24
Revises: cb9d5e0f1f0f
Create Date: 2026-08-28 22:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8b11c79c5e24"
down_revision: str | Sequence[str] | None = "cb9d5e0f1f0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("cron_expression", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=80), server_default="Asia/Shanghai", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "task_type IN ('token_refresh')",
            name=op.f("ck_schedules_task_type_values"),
        ),
        sa.ForeignKeyConstraint(
            ["last_job_id"],
            ["jobs.id"],
            name=op.f("fk_schedules_last_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedules")),
        sa.UniqueConstraint("name", name=op.f("uq_schedules_name")),
    )
    op.create_index("ix_schedules_due", "schedules", ["enabled", "next_run_at"], unique=False)
    op.create_table(
        "token_refresh_logs",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("reason_code", sa.String(length=96), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("rotated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('success','failed','skipped')",
            name=op.f("ck_token_refresh_logs_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_token_refresh_logs_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_token_refresh_logs_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_token_refresh_logs")),
    )
    op.create_index(
        "ix_token_refresh_logs_account_created",
        "token_refresh_logs",
        ["account_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_token_refresh_logs_account_created", table_name="token_refresh_logs")
    op.drop_table("token_refresh_logs")
    op.drop_index("ix_schedules_due", table_name="schedules")
    op.drop_table("schedules")
