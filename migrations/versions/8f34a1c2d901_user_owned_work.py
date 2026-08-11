"""user-owned work items

Revision ID: 8f34a1c2d901
Revises: 12916f19acec
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f34a1c2d901"
down_revision: Union[str, None] = "12916f19acec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("planned_start", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("planned_end", existing_type=sa.String(), nullable=False)

    with op.batch_alter_table("parts") as batch_op:
        batch_op.alter_column("planned_start", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("planned_end", existing_type=sa.String(), nullable=False)
        batch_op.add_column(sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_check_constraint("parts_active_bool", "is_active IN (0, 1)")

    with op.batch_alter_table("work_items") as batch_op:
        batch_op.alter_column("planned_start", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("planned_end", existing_type=sa.String(), nullable=False)
        batch_op.add_column(sa.Column("owner_user_id", sa.String(), nullable=False))
        batch_op.add_column(sa.Column("description", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"))
        batch_op.create_foreign_key(
            "fk_work_items_owner_user_id_users", "users", ["owner_user_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_check_constraint("work_items_active_bool", "is_active IN (0, 1)")
        batch_op.create_index("idx_work_items_owner_active", ["owner_user_id", "is_active"])

    with op.batch_alter_table("assignments") as batch_op:
        batch_op.drop_constraint("uq_assignments_work_item_user", type_="unique")
        batch_op.create_unique_constraint("uq_assignments_work_item", ["work_item_id"])


def downgrade() -> None:
    with op.batch_alter_table("assignments") as batch_op:
        batch_op.drop_constraint("uq_assignments_work_item", type_="unique")
        batch_op.create_unique_constraint("uq_assignments_work_item_user", ["work_item_id", "user_id"])

    with op.batch_alter_table("work_items") as batch_op:
        batch_op.drop_index("idx_work_items_owner_active")
        batch_op.drop_constraint("work_items_active_bool", type_="check")
        batch_op.drop_constraint("fk_work_items_owner_user_id_users", type_="foreignkey")
        batch_op.drop_column("is_active")
        batch_op.drop_column("description")
        batch_op.drop_column("owner_user_id")
        batch_op.alter_column("planned_end", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("planned_start", existing_type=sa.String(), nullable=True)

    with op.batch_alter_table("parts") as batch_op:
        batch_op.drop_constraint("parts_active_bool", type_="check")
        batch_op.drop_column("is_active")
        batch_op.alter_column("planned_end", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("planned_start", existing_type=sa.String(), nullable=True)

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("planned_end", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("planned_start", existing_type=sa.String(), nullable=True)
