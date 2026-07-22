from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from alembic import command
from alembic.config import Config

from backend.app.db.session import configure_database


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "backend" / "alembic.ini"


def _config(database_url: str) -> Config:
    configure_database(database_url)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_snapshot_migration_supports_three_adjustment_roles_and_round_trip(tmp_path):
    database_path = tmp_path / "snapshot-migration.db"
    config = _config(f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        indexes = connection.execute("PRAGMA index_list('snapshot_members')").fetchall()
        role_index = next(row[1] for row in indexes if row[2] == 1)
        columns = connection.execute(f"PRAGMA index_info('{role_index}')").fetchall()
        assert [row[2] for row in columns] == ["snapshot_id", "role"]
        connection.execute(
            "INSERT INTO snapshots(id, name, status, created_at) VALUES (1, 'first', 'active', CURRENT_TIMESTAMP)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO snapshots(id, name, status, created_at) VALUES (2, 'second', 'active', CURRENT_TIMESTAMP)"
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    command.downgrade(config, "a6b4d8e2f130")
    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "snapshots" not in tables
        assert "snapshot_members" not in tables

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"snapshots", "snapshot_members"} <= tables
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
