"""expand schedule task types

Revision ID: 9b27e6f43c81
Revises: 6f3d98c42b10
Create Date: 2026-08-28 23:50:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9b27e6f43c81"
down_revision: str | Sequence[str] | None = "6f3d98c42b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_schedules_task_type_values"), "schedules", type_="check")
    op.create_check_constraint(
        op.f("ck_schedules_task_type_values"),
        "schedules",
        "task_type IN ('token_refresh','retention_sync','forwarding','webdav_backup')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM schedules WHERE task_type != 'token_refresh'")
    op.drop_constraint(op.f("ck_schedules_task_type_values"), "schedules", type_="check")
    op.create_check_constraint(
        op.f("ck_schedules_task_type_values"),
        "schedules",
        "task_type IN ('token_refresh')",
    )
