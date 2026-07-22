from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
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

    from alembic import command
    from alembic.config import Config

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


def get_db() -> Iterator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
