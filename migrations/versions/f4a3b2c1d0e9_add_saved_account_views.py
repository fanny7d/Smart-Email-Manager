"""add saved account views

Revision ID: f4a3b2c1d0e9
Revises: e71c4a209d55
Create Date: 2026-08-29 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4a3b2c1d0e9"
down_revision: str | None = "e71c4a209d55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_account_views",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_account_views")),
        sa.UniqueConstraint("name", name=op.f("uq_saved_account_views_name")),
    )
    op.create_index(
        "ix_saved_account_views_sort",
        "saved_account_views",
        ["sort_order", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_saved_account_views_sort", table_name="saved_account_views")
    op.drop_table("saved_account_views")
