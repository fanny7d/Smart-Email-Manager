"""add forwarding engine

Revision ID: 4c2ef011d8a7
Revises: 1a9e76b30f42
Create Date: 2026-08-28 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4c2ef011d8a7"
down_revision: str | Sequence[str] | None = "1a9e76b30f42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forwarding_destinations",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "channel IN ('smtp','telegram','wecom')",
            name=op.f("ck_forwarding_destinations_channel_values"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forwarding_destinations")),
        sa.UniqueConstraint("name", name=op.f("uq_forwarding_destinations_name")),
    )
    op.create_table(
        "account_forwarding",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("include_junk", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("window_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cursor_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_forwarding_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_account_forwarding")),
    )
    op.create_table(
        "account_forwarding_destinations",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("destination_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account_forwarding.account_id"],
            name=op.f("fk_account_forwarding_destinations_account_id_account_forwarding"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["destination_id"],
            ["forwarding_destinations.id"],
            name=op.f("fk_account_forwarding_destinations_destination_id_forwarding_destinations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "account_id",
            "destination_id",
            name=op.f("pk_account_forwarding_destinations"),
        ),
    )
    op.create_table(
        "forwarding_deliveries",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("folder", sa.String(length=32), nullable=False),
        sa.Column("destination_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=96), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('processing','success','failed')",
            name=op.f("ck_forwarding_deliveries_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_forwarding_deliveries_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["destination_id"],
            ["forwarding_destinations.id"],
            name=op.f("fk_forwarding_deliveries_destination_id_forwarding_destinations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forwarding_deliveries")),
        sa.UniqueConstraint(
            "account_id",
            "message_id",
            "destination_id",
            name=op.f("uq_forwarding_deliveries_account_id"),
        ),
    )
    op.create_index(
        "ix_forwarding_deliveries_account_created",
        "forwarding_deliveries",
        ["account_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_forwarding_deliveries_account_created",
        table_name="forwarding_deliveries",
    )
    op.drop_table("forwarding_deliveries")
    op.drop_table("account_forwarding_destinations")
    op.drop_table("account_forwarding")
    op.drop_table("forwarding_destinations")
