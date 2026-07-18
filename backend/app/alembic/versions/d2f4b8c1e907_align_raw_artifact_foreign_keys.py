"""Align raw artifact foreign-key constraints across PostgreSQL and SQLite."""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


revision: str = "d2f4b8c1e907"
down_revision: Union[str, Sequence[str], None] = "c7e1a8d4b930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SYNC_FK = "fk_sync_tasks_input_raw_artifact"
_BATCH_FK = "fk_ingest_batches_raw_artifact"


def _has_fk(table: str, name: str, columns: list[str]) -> bool:
    return any(
        (
            fk.get("name") == name
            or (
                fk.get("referred_table") == "raw_artifacts"
                and fk.get("constrained_columns") == columns
                and fk.get("referred_columns") == ["id"]
            )
        )
        and (fk.get("options", {}).get("ondelete") or "").upper() == "RESTRICT"
        for fk in inspect(op.get_bind()).get_foreign_keys(table)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if not {"sync_tasks", "ingest_batches", "raw_artifacts"} <= tables:
        return

    if bind.dialect.name == "sqlite":
        if not _has_fk("sync_tasks", _SYNC_FK, ["input_raw_artifact_id"]):
            with op.batch_alter_table("sync_tasks", recreate="always") as batch:
                batch.create_foreign_key(
                    _SYNC_FK,
                    "raw_artifacts",
                    ["input_raw_artifact_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
        if not _has_fk("ingest_batches", _BATCH_FK, ["raw_artifact_id"]):
            with op.batch_alter_table("ingest_batches", recreate="always") as batch:
                batch.create_foreign_key(
                    _BATCH_FK,
                    "raw_artifacts",
                    ["raw_artifact_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
        return

    if not _has_fk("sync_tasks", _SYNC_FK, ["input_raw_artifact_id"]):
        op.create_foreign_key(
            _SYNC_FK,
            "sync_tasks",
            "raw_artifacts",
            ["input_raw_artifact_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    if not _has_fk("ingest_batches", _BATCH_FK, ["raw_artifact_id"]):
        op.create_foreign_key(
            _BATCH_FK,
            "ingest_batches",
            "raw_artifacts",
            ["raw_artifact_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if not {"sync_tasks", "ingest_batches", "raw_artifacts"} <= tables:
        return

    if bind.dialect.name == "sqlite":
        if _has_fk("ingest_batches", _BATCH_FK, ["raw_artifact_id"]):
            with op.batch_alter_table("ingest_batches", recreate="always") as batch:
                batch.drop_constraint(_BATCH_FK, type_="foreignkey")
        if _has_fk("sync_tasks", _SYNC_FK, ["input_raw_artifact_id"]):
            with op.batch_alter_table("sync_tasks", recreate="always") as batch:
                batch.drop_constraint(_SYNC_FK, type_="foreignkey")
        return

    if _has_fk("ingest_batches", _BATCH_FK, ["raw_artifact_id"]):
        op.drop_constraint(_BATCH_FK, "ingest_batches", type_="foreignkey")
    if _has_fk("sync_tasks", _SYNC_FK, ["input_raw_artifact_id"]):
        op.drop_constraint(_SYNC_FK, "sync_tasks", type_="foreignkey")
