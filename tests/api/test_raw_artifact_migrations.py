from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.app.db.base import Base
from backend.app.db.session import configure_database, get_engine
from backend.app.models import entities  # noqa: F401


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[2]
    config = Config()
    config.set_main_option("script_location", str(project_root / "backend" / "app" / "alembic"))
    return config


def test_raw_artifact_fk_migration_downgrades_after_fresh_metadata_create(tmp_path):
    """Fresh metadata schemas have unnamed SQLite FKs that migration must normalize."""
    configure_database(f"sqlite:///{tmp_path / 'fresh-schema.db'}")
    Base.metadata.create_all(bind=get_engine())
    config = _alembic_config()

    command.upgrade(config, "head")
    command.downgrade(config, "c7e1a8d4b930")
    command.upgrade(config, "head")


def test_raw_artifact_fk_migration_replaces_wrong_delete_policy_without_duplication(tmp_path):
    """Legacy raw FKs with NO ACTION become one RESTRICT FK per reference column."""
    database_path = tmp_path / "legacy-raw-fk.db"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE raw_artifacts (id INTEGER PRIMARY KEY);
            CREATE TABLE sync_tasks (
              id INTEGER PRIMARY KEY,
              task_type VARCHAR(64),
              status VARCHAR(32),
              adjust_type VARCHAR(16),
              input_raw_artifact_id INTEGER,
              FOREIGN KEY(input_raw_artifact_id) REFERENCES raw_artifacts(id) ON DELETE NO ACTION
            );
            CREATE TABLE ingest_batches (
              id INTEGER PRIMARY KEY,
              raw_artifact_id INTEGER,
              FOREIGN KEY(raw_artifact_id) REFERENCES raw_artifacts(id) ON DELETE NO ACTION
            );
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
            INSERT INTO alembic_version(version_num) VALUES ('c7e1a8d4b930');
            """
        )
        connection.commit()
    finally:
        connection.close()

    configure_database(f"sqlite:///{database_path}")
    command.upgrade(_alembic_config(), "head")

    connection = sqlite3.connect(database_path)
    try:
        for table, column in (
            ("sync_tasks", "input_raw_artifact_id"),
            ("ingest_batches", "raw_artifact_id"),
        ):
            foreign_keys = [
                foreign_key
                for foreign_key in connection.execute(f"PRAGMA foreign_key_list({table})")
                if foreign_key[2] == "raw_artifacts" and foreign_key[3] == column
            ]
            assert len(foreign_keys) == 1
            assert foreign_keys[0][6] == "RESTRICT"
    finally:
        connection.close()


def test_active_replay_index_migration_keeps_lowest_id_and_fails_legacy_duplicates(tmp_path):
    database_path = tmp_path / "legacy-active-replays.db"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE raw_artifacts (id INTEGER PRIMARY KEY);
            INSERT INTO raw_artifacts(id) VALUES (1);
            CREATE TABLE sync_tasks (
              id INTEGER PRIMARY KEY,
              task_type VARCHAR(64),
              status VARCHAR(32),
              adjust_type VARCHAR(16),
              input_raw_artifact_id INTEGER,
              error_message TEXT,
              progress INTEGER NOT NULL DEFAULT 0,
              finished_at DATETIME
            );
            INSERT INTO sync_tasks(id, task_type, status, adjust_type, input_raw_artifact_id)
            VALUES
              (12, 'daily_bars_raw_replay', 'pending', 'none', 1),
              (10, 'daily_bars_raw_replay', 'running', NULL, 1),
              (11, 'daily_bars_raw_replay', 'pending', 'none', 1);
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
            INSERT INTO alembic_version(version_num) VALUES ('d2f4b8c1e907');
            """
        )
        connection.commit()
    finally:
        connection.close()

    configure_database(f"sqlite:///{database_path}")
    command.upgrade(_alembic_config(), "head")

    connection = sqlite3.connect(database_path)
    try:
        tasks = connection.execute(
            "SELECT id, status, error_message, progress, finished_at, adjust_type FROM sync_tasks ORDER BY id"
        ).fetchall()
        assert tasks[0][0] == 10
        assert tasks[0][1] == "running"
        assert tasks[0][5] == "none"
        assert tasks[1][1] == "failed"
        assert tasks[2][1] == "failed"
        assert all(task[3] == 100 and task[4] is not None for task in tasks[1:])
        assert all("survivor task id=10" in task[2] for task in tasks[1:])
        index_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_sync_tasks_active_raw_replay'"
        ).fetchone()[0]
        assert "WHERE task_type" in index_sql
    finally:
        connection.close()
