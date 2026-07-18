"""Make active raw replay task identity database-enforced."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f3a9c5d7e812"
down_revision: Union[str, Sequence[str], None] = "d2f4b8c1e907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_sync_tasks_active_raw_replay"
_REQUIRED_COLUMNS = {"task_type", "status", "input_raw_artifact_id", "adjust_type"}
_PREDICATE = "task_type = 'daily_bars_raw_replay' AND status IN ('pending', 'running')"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "sync_tasks" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("sync_tasks")}
    if not _REQUIRED_COLUMNS <= columns:
        return
    indexes = {index["name"] for index in inspector.get_indexes("sync_tasks")}
    if _INDEX in indexes:
        return
    if bind.dialect.name == "sqlite":
        op.execute(
            sa.text(
                f"CREATE UNIQUE INDEX {_INDEX} ON sync_tasks "
                f"(input_raw_artifact_id, adjust_type) WHERE {_PREDICATE}"
            )
        )
        return
    op.create_index(
        _INDEX,
        "sync_tasks",
        ["input_raw_artifact_id", "adjust_type"],
        unique=True,
        postgresql_where=sa.text(_PREDICATE),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "sync_tasks" not in inspector.get_table_names():
        return
    if _INDEX in {index["name"] for index in inspector.get_indexes("sync_tasks")}:
        op.drop_index(_INDEX, table_name="sync_tasks")
