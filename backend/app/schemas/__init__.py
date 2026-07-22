"""Pydantic schemas for API request and response bodies."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response. Use as ``PaginatedResponse[MyModel]``."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

