"""add proxy health probes

Revision ID: d2a63f74c901
Revises: b4f2918e3d60
Create Date: 2026-08-29 01:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2a63f74c901"
down_revision: str | Sequence[str] | None = "b4f2918e3d60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proxy_profiles",
        sa.Column("health_status", sa.String(length=32), server_default="unknown", nullable=False),
    )
    op.add_column(
        "proxy_profiles",
        sa.Column("health_reason_code", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "proxy_profiles",
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proxy_profiles", "last_tested_at")
    op.drop_column("proxy_profiles", "health_reason_code")
    op.drop_column("proxy_profiles", "health_status")
