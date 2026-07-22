"""Add immutable research snapshot metadata."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b7c9e1f4a260"
down_revision: Union[str, Sequence[str], None] = "a6b4d8e2f130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    if "snapshots" not in existing:
        op.create_table(
            "snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        op.create_index("ix_snapshots_name", "snapshots", ["name"])
        op.create_index("ix_snapshots_status", "snapshots", ["status"])

    existing = set(inspect(bind).get_table_names())
    if "snapshot_members" not in existing:
        op.create_table(
            "snapshot_members",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("snapshot_id", sa.Integer(), nullable=False),
            sa.Column("dataset_id", sa.Integer(), nullable=False),
            sa.Column("dataset_version_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(32), nullable=False, server_default="bars"),
            sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("snapshot_id", "role", name="uq_snapshot_role"),
        )
        op.create_index("ix_snapshot_members_snapshot_id", "snapshot_members", ["snapshot_id"])
        op.create_index("ix_snapshot_members_dataset_id", "snapshot_members", ["dataset_id"])
        op.create_index(
            "ix_snapshot_members_dataset_version_id",
            "snapshot_members",
            ["dataset_version_id"],
        )

    indexes = {index["name"] for index in inspect(bind).get_indexes("snapshots")}
    if "uq_snapshots_active" not in indexes:
        if bind.dialect.name == "sqlite":
            op.execute("CREATE UNIQUE INDEX uq_snapshots_active ON snapshots(status) WHERE status = 'active'")
        else:
            op.create_index(
                "uq_snapshots_active",
                "snapshots",
                ["status"],
                unique=True,
                postgresql_where=sa.text("status = 'active'"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    if "snapshot_members" in existing:
        op.drop_table("snapshot_members")
    existing = set(inspect(bind).get_table_names())
    if "snapshots" in existing:
        op.drop_index("uq_snapshots_active", table_name="snapshots")
        op.drop_table("snapshots")
