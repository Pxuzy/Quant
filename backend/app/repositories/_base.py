"""Base class for SQLAlchemy repository layer."""

from __future__ import annotations

from sqlalchemy.orm import Session


class BaseRepository:
    """Shared base for all session-based repositories.

    Subclasses define domain-specific query methods on top of ``self.db``.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
