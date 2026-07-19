"""Add the raw artifact input reference used by offline replay tasks."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "a4d2f7e91c30"
down_revision: Union[str, Sequence[str], None] = "9c1f4e6b7a2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "sync_tasks" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("sync_tasks")}
    if "input_raw_artifact_id" in columns:
        return

    op.add_column("sync_tasks", sa.Column("input_raw_artifact_id", sa.Integer(), nullable=True))
    op.create_index("ix_sync_tasks_input_raw_artifact_id", "sync_tasks", ["input_raw_artifact_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "sync_tasks" not in inspector.get_table_names():
        return

    indexes = {index["name"] for index in inspector.get_indexes("sync_tasks")}
    if "ix_sync_tasks_input_raw_artifact_id" in indexes:
        op.drop_index("ix_sync_tasks_input_raw_artifact_id", table_name="sync_tasks")
    columns = {column["name"] for column in inspect(bind).get_columns("sync_tasks")}
    if "input_raw_artifact_id" in columns:
        op.drop_column("sync_tasks", "input_raw_artifact_id")
