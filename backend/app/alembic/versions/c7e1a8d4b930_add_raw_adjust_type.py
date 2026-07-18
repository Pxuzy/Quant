"""Record the actual adjustment semantics of raw daily-bar artifacts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "c7e1a8d4b930"
down_revision: Union[str, Sequence[str], None] = "b9e6c3d42f18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "raw_artifacts" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("raw_artifacts")}
    if "adjust_type" not in columns:
        op.add_column("raw_artifacts", sa.Column("adjust_type", sa.String(length=16), nullable=True))
        op.create_index("ix_raw_artifacts_adjust_type", "raw_artifacts", ["adjust_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "raw_artifacts" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("raw_artifacts")}
    if "ix_raw_artifacts_adjust_type" in indexes:
        op.drop_index("ix_raw_artifacts_adjust_type", table_name="raw_artifacts")
    columns = {column["name"] for column in inspect(bind).get_columns("raw_artifacts")}
    if "adjust_type" in columns:
        op.drop_column("raw_artifacts", "adjust_type")
