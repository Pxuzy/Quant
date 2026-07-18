"""Add immutable raw artifact metadata and link it to ingest batches."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "9c1f4e6b7a2d"
down_revision: Union[str, Sequence[str], None] = "7fce16dfa838"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "raw_artifacts" not in existing_tables:
        op.create_table(
            "raw_artifacts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("dataset_name", sa.String(128), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("requested_source", sa.String(64), nullable=False),
            sa.Column("market", sa.String(32), nullable=True),
            sa.Column("symbol", sa.String(32), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("uri", sa.String(1024), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content_type", sa.String(128), nullable=False, server_default="application/json"),
            sa.Column("status", sa.String(32), nullable=False, server_default="stored"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["sync_tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = inspect(bind)
    raw_indexes = {index["name"] for index in inspector.get_indexes("raw_artifacts")}
    for name, column in (
        ("ix_raw_artifacts_task_id", "task_id"),
        ("ix_raw_artifacts_dataset_name", "dataset_name"),
        ("ix_raw_artifacts_source", "source"),
        ("ix_raw_artifacts_requested_source", "requested_source"),
        ("ix_raw_artifacts_market", "market"),
        ("ix_raw_artifacts_symbol", "symbol"),
        ("ix_raw_artifacts_sha256", "sha256"),
        ("ix_raw_artifacts_status", "status"),
    ):
        if name not in raw_indexes:
            op.create_index(name, "raw_artifacts", [column], unique=False)

    if "ingest_batches" not in existing_tables:
        return

    ingest_columns = {column["name"] for column in inspect(bind).get_columns("ingest_batches")}
    if "raw_artifact_id" not in ingest_columns:
        op.add_column("ingest_batches", sa.Column("raw_artifact_id", sa.Integer(), nullable=True))
        op.create_index("ix_ingest_batches_raw_artifact_id", "ingest_batches", ["raw_artifact_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "ingest_batches" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("ingest_batches")}
        if "ix_ingest_batches_raw_artifact_id" in indexes:
            op.drop_index("ix_ingest_batches_raw_artifact_id", table_name="ingest_batches")
        columns = {column["name"] for column in inspect(bind).get_columns("ingest_batches")}
        if "raw_artifact_id" in columns:
            op.drop_column("ingest_batches", "raw_artifact_id")

    if "raw_artifacts" in inspect(bind).get_table_names():
        op.drop_table("raw_artifacts")
