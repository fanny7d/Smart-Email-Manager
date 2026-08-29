"""add work projects and leases

Revision ID: b4f2918e3d60
Revises: a8c0e15d7f33
Create Date: 2026-08-29 00:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4f2918e3d60"
down_revision: str | Sequence[str] | None = "a8c0e15d7f33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_projects",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("default_lease_seconds", sa.Integer(), server_default="300", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','paused','completed')",
            name=op.f("ck_work_projects_status_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_projects")),
        sa.UniqueConstraint("name", name=op.f("uq_work_projects_name")),
    )
    op.create_table(
        "project_accounts",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="to_claim", nullable=False),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_token_hash", sa.LargeBinary(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('to_claim','leased','done','failed','removed')",
            name=op.f("ck_project_accounts_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_project_accounts_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["work_projects.id"],
            name=op.f("fk_project_accounts_project_id_work_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_accounts")),
        sa.UniqueConstraint(
            "project_id",
            "account_id",
            name=op.f("uq_project_accounts_project_id"),
        ),
    )
    op.create_index(
        "ix_project_accounts_claim",
        "project_accounts",
        ["project_id", "status", "lease_expires_at"],
        unique=False,
    )
    op.create_table(
        "project_events",
        sa.Column("sequence", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("project_account_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=True),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_account_id"],
            ["project_accounts.id"],
            name=op.f("fk_project_events_project_account_id_project_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["work_projects.id"],
            name=op.f("fk_project_events_project_id_work_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sequence", name=op.f("pk_project_events")),
    )


def downgrade() -> None:
    op.drop_table("project_events")
    op.drop_index("ix_project_accounts_claim", table_name="project_accounts")
    op.drop_table("project_accounts")
    op.drop_table("work_projects")
