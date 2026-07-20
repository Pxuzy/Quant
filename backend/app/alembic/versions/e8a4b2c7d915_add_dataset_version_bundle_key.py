"""Add the release bundle identity shared by adjustment variants."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "e8a4b2c7d915"
down_revision: Union[str, Sequence[str], None] = "0c6e4a2d91f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "dataset_versions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("dataset_versions")}
    if "bundle_key" not in columns:
        op.add_column("dataset_versions", sa.Column("bundle_key", sa.String(64), nullable=True))
    indexes = {index["name"] for index in inspect(bind).get_indexes("dataset_versions")}
    if "ix_dataset_versions_bundle_key" not in indexes:
        op.create_index("ix_dataset_versions_bundle_key", "dataset_versions", ["bundle_key"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "dataset_versions" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("dataset_versions")}
    if "ix_dataset_versions_bundle_key" in indexes:
        op.drop_index("ix_dataset_versions_bundle_key", table_name="dataset_versions")
    columns = {column["name"] for column in inspect(bind).get_columns("dataset_versions")}
    if "bundle_key" in columns:
        op.drop_column("dataset_versions", "bundle_key")
