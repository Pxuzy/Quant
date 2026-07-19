"""Make active raw replay task identity database-enforced."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import func, inspect, select, update


revision: str = "f3a9c5d7e812"
down_revision: Union[str, Sequence[str], None] = "d2f4b8c1e907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_sync_tasks_active_raw_replay"
_REQUIRED_COLUMNS = {"task_type", "status", "input_raw_artifact_id", "adjust_type"}
_PREDICATE = "task_type = 'daily_bars_raw_replay' AND status IN ('pending', 'running')"


def _normalize_legacy_raw_replay_adjust_types(bind) -> None:
    active = sa.table(
        "sync_tasks",
        sa.column("task_type"),
        sa.column("adjust_type"),
    )
    bind.execute(
        update(active)
        .where(
            active.c.task_type == "daily_bars_raw_replay",
            active.c.adjust_type.is_(None),
        )
        .values(adjust_type="none")
    )


def _mark_duplicate_active_replays_failed(bind) -> None:
    active = sa.table(
        "sync_tasks",
        sa.column("id"),
        sa.column("task_type"),
        sa.column("status"),
        sa.column("input_raw_artifact_id"),
        sa.column("adjust_type"),
        sa.column("error_message"),
        sa.column("progress"),
        sa.column("finished_at"),
    )
    duplicate_groups = bind.execute(
        select(
            active.c.input_raw_artifact_id,
            active.c.adjust_type,
            func.min(active.c.id).label("survivor_id"),
        )
        .where(
            active.c.task_type == "daily_bars_raw_replay",
            active.c.status.in_(["pending", "running"]),
            active.c.input_raw_artifact_id.is_not(None),
        )
        .group_by(active.c.input_raw_artifact_id, active.c.adjust_type)
        .having(func.count(active.c.id) > 1)
    ).mappings()
    for group in duplicate_groups:
        bind.execute(
            update(active)
            .where(
                active.c.task_type == "daily_bars_raw_replay",
                active.c.status.in_(["pending", "running"]),
                active.c.input_raw_artifact_id == group["input_raw_artifact_id"],
                active.c.adjust_type == group["adjust_type"],
                active.c.id != group["survivor_id"],
            )
            .values(
                status="failed",
                progress=100,
                finished_at=func.now(),
                error_message="Superseded by active replay identity migration; survivor task id=" + str(group["survivor_id"]),
            )
        )


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
    _normalize_legacy_raw_replay_adjust_types(bind)
    _mark_duplicate_active_replays_failed(bind)
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
