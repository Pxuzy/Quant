from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import ensure_database_parent, get_settings
from backend.app.db.base import Base


_engine: Engine | None = None
_engine_url: str | None = None
_database_url_override: str | None = None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, future=True)


def configure_database(database_url: str | None = None) -> Engine:
    global _database_url_override, _engine, _engine_url

    _database_url_override = database_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
    return get_engine()


def get_database_url() -> str:
    return _database_url_override or get_settings().database_url


def _is_pg(url: str) -> bool:
    return url.startswith("postgresql")


def _get_sqlite_connect_args() -> dict:
    return {"check_same_thread": False}


def _setup_sqlite_pragmas(engine: Engine) -> None:
    """Enable SQLite integrity and concurrency pragmas for every connection."""
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def get_engine() -> Engine:
    global _engine, _engine_url

    database_url = get_database_url()
    if _engine is not None and _engine_url == database_url:
        return _engine

    ensure_database_parent(database_url)
    connect_args = {} if _is_pg(database_url) else _get_sqlite_connect_args()

    if _is_pg(database_url):
        _engine = create_engine(
            database_url,
            connect_args=connect_args,
            pool_size=5,
            max_overflow=10,
            future=True,
        )
    else:
        _engine = create_engine(database_url, connect_args=connect_args, future=True)
        _setup_sqlite_pragmas(_engine)

    _engine_url = database_url
    SessionLocal.configure(bind=_engine)
    return _engine


def _ensure_pg_extensions(engine: Engine) -> None:
    """Ensure PostgreSQL extensions exist."""
    if not _is_pg(engine.url.render_as_string(hide_password=False)):
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def _run_alembic_upgrade(engine: Engine) -> None:
    """Run Alembic migrations against the given engine."""
    from pathlib import Path

    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config()
    project_root = Path(__file__).resolve().parents[3]
    alembic_cfg.set_main_option("script_location", str(project_root / "backend" / "app" / "alembic"))
    # Point Alembic at our URL so it doesn't re-read env.py's hardcoded URL
    alembic_cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    command.upgrade(alembic_cfg, "head")


def init_db(*, drop_all: bool = False) -> None:
    from backend.app.models import entities  # noqa: F401

    engine = get_engine()

    if _is_pg(engine.url.render_as_string(hide_password=False)):
        _ensure_pg_extensions(engine)
    else:
        if drop_all:
            Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    _run_alembic_upgrade(engine)


def _ensure_sqlite_sync_task_columns(engine: Engine) -> None:
    if not engine.url.drivername.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "sync_tasks" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("sync_tasks")}
    required_columns = {
        "max_symbols": "INTEGER",
        "start_policy": "VARCHAR(32)",
        "adjust_type": "VARCHAR(16)",
        "input_raw_artifact_id": "INTEGER",
        "failed_symbols": "JSON NOT NULL DEFAULT '[]'",
        "failed_chunks": "JSON NOT NULL DEFAULT '[]'",
        "failure_reason": "TEXT",
        "heartbeat_at": "DATETIME",
        "lease_owner": "VARCHAR(128)",
        "lease_expires_at": "DATETIME",
        "attempt": "INTEGER NOT NULL DEFAULT 0",
    }
    missing_columns = [
        (name, column_type)
        for name, column_type in required_columns.items()
        if name not in existing_columns
    ]
    if not missing_columns:
        return

    with engine.begin() as connection:
        for name, column_type in missing_columns:
            connection.execute(text(f"ALTER TABLE sync_tasks ADD COLUMN {name} {column_type}"))


def _ensure_sqlite_ingest_batch_columns(engine: Engine) -> None:
    if not engine.url.drivername.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "ingest_batches" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("ingest_batches")}
    with engine.begin() as connection:
        if "raw_artifact_id" not in existing_columns:
            connection.execute(text("ALTER TABLE ingest_batches ADD COLUMN raw_artifact_id INTEGER"))
        if "dropped_records" not in existing_columns:
            connection.execute(text("ALTER TABLE ingest_batches ADD COLUMN dropped_records INTEGER NOT NULL DEFAULT 0"))


def _ensure_sqlite_raw_artifact_columns(engine: Engine) -> None:
    if not engine.url.drivername.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "raw_artifacts" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("raw_artifacts")}
    if "adjust_type" not in existing_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE raw_artifacts ADD COLUMN adjust_type VARCHAR(16)"))


def get_db() -> Iterator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
