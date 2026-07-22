"""Record normalization-loss counts on ingest batches."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b9e6c3d42f18"
down_revision: Union[str, Sequence[str], None] = "a4d2f7e91c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "ingest_batches" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("ingest_batches")}
    if "dropped_records" not in columns:
        op.add_column(
            "ingest_batches",
            sa.Column("dropped_records", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "ingest_batches" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("ingest_batches")}
    if "dropped_records" in columns:
        op.drop_column("ingest_batches", "dropped_records")
