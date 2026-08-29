"""add account bulk previews

Revision ID: f6b7c8d9e0a1
Revises: f4a3b2c1d0e9
Create Date: 2026-08-29 00:38:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6b7c8d9e0a1"
down_revision: str | None = "f4a3b2c1d0e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_bulk_previews",
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "selection",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "mutation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "account_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("dangerous_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_bulk_previews")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_account_bulk_previews_token_hash")),
    )
    op.create_index(
        "ix_account_bulk_previews_expiry",
        "account_bulk_previews",
        ["expires_at", "consumed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_account_bulk_previews_expiry", table_name="account_bulk_previews")
    op.drop_table("account_bulk_previews")
