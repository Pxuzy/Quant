"""Add task leases, heartbeat, attempts, and partial-failure details."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0c6e4a2d91f7"
down_revision: Union[str, Sequence[str], None] = "b7c9e1f4a260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = {
    "failed_symbols": sa.JSON(),
    "failed_chunks": sa.JSON(),
    "failure_reason": sa.Text(),
    "heartbeat_at": sa.DateTime(timezone=True),
    "lease_owner": sa.String(128),
    "lease_expires_at": sa.DateTime(timezone=True),
    "attempt": sa.Integer(),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "sync_tasks" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("sync_tasks")}
    for name, column_type in _COLUMNS.items():
        if name not in existing:
            kwargs = {"nullable": False, "server_default": "0"} if name == "attempt" else {"nullable": True}
            if name in {"failed_symbols", "failed_chunks"}:
                kwargs = {"nullable": False, "server_default": "[]"}
            op.add_column("sync_tasks", sa.Column(name=name, type_=column_type, **kwargs))
    indexes = {index["name"] for index in inspect(bind).get_indexes("sync_tasks")}
    if "ix_sync_tasks_lease_owner" not in indexes:
        op.create_index("ix_sync_tasks_lease_owner", "sync_tasks", ["lease_owner"], unique=False)
    if "ix_sync_tasks_lease_expires_at" not in indexes:
        op.create_index("ix_sync_tasks_lease_expires_at", "sync_tasks", ["lease_expires_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "sync_tasks" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspect(bind).get_indexes("sync_tasks")}
    for index_name in ("ix_sync_tasks_lease_expires_at", "ix_sync_tasks_lease_owner"):
        if index_name in indexes:
            op.drop_index(index_name, table_name="sync_tasks")
    columns = {column["name"] for column in inspect(bind).get_columns("sync_tasks")}
    for name in reversed(list(_COLUMNS)):
        if name in columns:
            op.drop_column("sync_tasks", name)
