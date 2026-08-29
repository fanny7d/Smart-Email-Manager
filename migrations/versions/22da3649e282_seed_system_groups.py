"""seed system groups

Revision ID: 22da3649e282
Revises: cfa1cb5db0e8
Create Date: 2026-08-28 20:58:15.420232
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "22da3649e282"
down_revision: str | Sequence[str] | None = "cfa1cb5db0e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO groups (id, name, description, color, sort_order, level, system_key)
            SELECT uuidv7(), '默认分组', 'Default mailbox group', '#64748b', 1, 1, 'default'
            WHERE NOT EXISTS (SELECT 1 FROM groups WHERE system_key = 'default')
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO groups (id, name, description, color, sort_order, level, system_key)
            SELECT uuidv7(), '临时邮箱', 'Temporary mailbox providers', '#0ea5e9', 0, 1, 'temporary'
            WHERE NOT EXISTS (SELECT 1 FROM groups WHERE system_key = 'temporary')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE accounts
            SET group_id = (SELECT id FROM groups WHERE system_key = 'default')
            WHERE group_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE accounts
            SET group_id = NULL
            WHERE group_id IN (SELECT id FROM groups WHERE system_key IN ('default', 'temporary'))
            """
        )
    )
    op.execute(sa.text("DELETE FROM groups WHERE system_key IN ('default', 'temporary')"))
