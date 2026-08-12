"""remove unused personal schedules and calendar models

Revision ID: 6c842f51d7a3
Revises: 8f34a1c2d901
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c842f51d7a3"
down_revision: Union[str, None] = "8f34a1c2d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("assignment_progress") as batch_op:
        batch_op.drop_constraint("assignment_progress_period", type_="check")
        batch_op.drop_column("schedule_end")
        batch_op.drop_column("schedule_start")
    op.drop_table("personal_notes")
    op.drop_table("calendar_events")
    with op.batch_alter_table("sync_state") as batch_op:
        batch_op.add_column(sa.Column("base_snapshot_json", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sync_state") as batch_op:
        batch_op.drop_column("base_snapshot_json")
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("start_at", sa.String(), nullable=False),
        sa.Column("end_at", sa.String(), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("memo", sa.String(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "personal_notes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=True),
        sa.Column("is_pinned", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("is_deleted", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("assignment_progress") as batch_op:
        batch_op.add_column(sa.Column("schedule_start", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("schedule_end", sa.String(), nullable=True))
        batch_op.create_check_constraint(
            "assignment_progress_period",
            "schedule_end IS NULL OR schedule_start IS NULL OR schedule_end >= schedule_start",
        )
