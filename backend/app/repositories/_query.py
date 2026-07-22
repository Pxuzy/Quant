"""Shared query helpers for repository layer."""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def paginated_query(
    db: Session,
    *,
    model: type,
    conditions: list,
    order_by: Sequence,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list, int]:
    """Execute a paginated SELECT query with conditions.

    Returns (records, total_count). Both count and records queries
    share the same WHERE conditions to stay consistent.
    """
    total_stmt = select(func.count(model.id))
    records_stmt = select(model).order_by(*order_by)

    if conditions:
        total_stmt = total_stmt.where(*conditions)
        records_stmt = records_stmt.where(*conditions)

    total = db.scalar(total_stmt) or 0
    if page > 0 and page_size > 0:
        records_stmt = records_stmt.offset((page - 1) * page_size).limit(page_size)
    records = list(db.scalars(records_stmt).all())
    return records, total
