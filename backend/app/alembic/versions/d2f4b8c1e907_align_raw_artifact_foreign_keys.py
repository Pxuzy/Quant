"""Align raw artifact foreign-key constraints across PostgreSQL and SQLite."""

from typing import Any, Mapping, Sequence, Union

from alembic import op
from sqlalchemy import inspect


revision: str = "d2f4b8c1e907"
down_revision: Union[str, Sequence[str], None] = "c7e1a8d4b930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SYNC_FK = "fk_sync_tasks_input_raw_artifact"
_BATCH_FK = "fk_ingest_batches_raw_artifact"
_SQLITE_FK_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _raw_artifact_fks(table: str, columns: list[str]) -> list[Mapping[str, Any]]:
    return [
        foreign_key
        for foreign_key in inspect(op.get_bind()).get_foreign_keys(table)
        if foreign_key.get("referred_table") == "raw_artifacts"
        and foreign_key.get("constrained_columns") == columns
        and foreign_key.get("referred_columns") == ["id"]
    ]


def _is_restrict_raw_artifact_fk(foreign_key: Mapping[str, Any]) -> bool:
    return (foreign_key.get("options", {}).get("ondelete") or "").upper() == "RESTRICT"


def _has_exactly_one_restrict_raw_artifact_fk(table: str, columns: list[str]) -> bool:
    foreign_keys = _raw_artifact_fks(table, columns)
    return len(foreign_keys) == 1 and _is_restrict_raw_artifact_fk(foreign_keys[0])


def _drop_sqlite_raw_artifact_fks(table: str, columns: list[str]) -> None:
    foreign_keys = _raw_artifact_fks(table, columns)
    if not foreign_keys:
        return
    with op.batch_alter_table(
        table,
        recreate="always",
        naming_convention=_SQLITE_FK_NAMING,
    ) as batch:
        for foreign_key in foreign_keys:
            constraint_name = foreign_key.get("name") or _SQLITE_FK_NAMING["fk"] % {
                "table_name": table,
                "column_0_name": columns[0],
                "referred_table_name": "raw_artifacts",
            }
            batch.drop_constraint(constraint_name, type_="foreignkey")


def _rebuild_sqlite_raw_artifact_fk(table: str, name: str, columns: list[str]) -> None:
    _drop_sqlite_raw_artifact_fks(table, columns)
    with op.batch_alter_table(
        table,
        recreate="always",
        naming_convention=_SQLITE_FK_NAMING,
    ) as batch:
        batch.create_foreign_key(name, "raw_artifacts", columns, ["id"], ondelete="RESTRICT")


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if not {"sync_tasks", "ingest_batches", "raw_artifacts"} <= tables:
        return

    constraints = (
        ("sync_tasks", _SYNC_FK, ["input_raw_artifact_id"]),
        ("ingest_batches", _BATCH_FK, ["raw_artifact_id"]),
    )
    if bind.dialect.name == "sqlite":
        for table, name, columns in constraints:
            if not _has_exactly_one_restrict_raw_artifact_fk(table, columns):
                _rebuild_sqlite_raw_artifact_fk(table, name, columns)
        return

    for table, name, columns in constraints:
        foreign_keys = _raw_artifact_fks(table, columns)
        if len(foreign_keys) == 1 and _is_restrict_raw_artifact_fk(foreign_keys[0]):
            continue
        for foreign_key in foreign_keys:
            if not foreign_key.get("name"):
                raise RuntimeError(
                    f"Cannot normalize unnamed raw artifact foreign key on {table}.{columns[0]} outside SQLite."
                )
            op.drop_constraint(foreign_key["name"], table, type_="foreignkey")
        op.create_foreign_key(name, table, "raw_artifacts", columns, ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if not {"sync_tasks", "ingest_batches", "raw_artifacts"} <= tables:
        return

    constraints = (
        ("ingest_batches", ["raw_artifact_id"]),
        ("sync_tasks", ["input_raw_artifact_id"]),
    )
    if bind.dialect.name == "sqlite":
        for table, columns in constraints:
            _drop_sqlite_raw_artifact_fks(table, columns)
        return

    for table, columns in constraints:
        for foreign_key in _raw_artifact_fks(table, columns):
            if foreign_key.get("name"):
                op.drop_constraint(foreign_key["name"], table, type_="foreignkey")
