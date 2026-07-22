"""Add immutable dataset version and partition metadata."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "a6b4d8e2f130"
down_revision: Union[str, Sequence[str], None] = "f3a9c5d7e812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    if "dataset_versions" not in existing:
        op.create_table(
            "dataset_versions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("dataset_id", sa.Integer(), nullable=False),
            sa.Column("version_seq", sa.Integer(), nullable=False),
            sa.Column("version_key", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="candidate"),
            sa.Column("schema_version", sa.String(32), nullable=False),
            sa.Column("normalize_version", sa.String(32), nullable=False),
            sa.Column("schema_sha256", sa.String(64), nullable=False),
            sa.Column("adjust_type", sa.String(16), nullable=False),
            sa.Column("quality_policy_version", sa.String(64), nullable=True),
            sa.Column("quality_status", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_trade_date", sa.Date(), nullable=True),
            sa.Column("max_trade_date", sa.Date(), nullable=True),
            sa.Column("manifest_uri", sa.String(512), nullable=False),
            sa.Column("manifest_sha256", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dataset_id", "version_seq", name="uq_dataset_versions_sequence"),
            sa.UniqueConstraint("dataset_id", "version_key", name="uq_dataset_versions_key"),
            sa.UniqueConstraint("dataset_id", "manifest_sha256", name="uq_dataset_versions_manifest"),
        )
        op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])
        op.create_index("ix_dataset_versions_status", "dataset_versions", ["status"])

    existing = set(inspect(bind).get_table_names())
    if "dataset_version_partitions" not in existing:
        op.create_table(
            "dataset_version_partitions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("dataset_version_id", sa.Integer(), nullable=False),
            sa.Column("partition_spec_json", sa.JSON(), nullable=False),
            sa.Column("relative_uri", sa.String(512), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("byte_size", sa.Integer(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("min_trade_date", sa.Date(), nullable=True),
            sa.Column("max_trade_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="sealed"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "dataset_version_id",
                "partition_spec_json",
                "relative_uri",
                name="uq_dataset_version_partitions_identity",
            ),
        )
        op.create_index(
            "ix_dataset_version_partitions_dataset_version_id",
            "dataset_version_partitions",
            ["dataset_version_id"],
        )
        op.create_index("ix_dataset_version_partitions_status", "dataset_version_partitions", ["status"])


def downgrade() -> None:
    existing = set(inspect(op.get_bind()).get_table_names())
    if "dataset_version_partitions" in existing:
        op.drop_table("dataset_version_partitions")
    existing = set(inspect(op.get_bind()).get_table_names())
    if "dataset_versions" in existing:
        op.drop_table("dataset_versions")
