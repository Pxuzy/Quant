from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.core.config import ensure_database_parent, get_settings
from apps.api.db.base import Base


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


def get_engine() -> Engine:
    global _engine, _engine_url

    database_url = get_database_url()
    if _engine is not None and _engine_url == database_url:
        return _engine

    ensure_database_parent(database_url)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    _engine = create_engine(database_url, connect_args=connect_args, future=True)
    _engine_url = database_url
    
    # Set SQLite busy timeout to 30 seconds (30000ms)
    # This prevents "database is locked" errors during concurrent writes
    if database_url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    
    SessionLocal.configure(bind=_engine)
    return _engine


def init_db(*, drop_all: bool = False) -> None:
    from apps.api.models import entities  # noqa: F401

    engine = get_engine()
    if drop_all:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

