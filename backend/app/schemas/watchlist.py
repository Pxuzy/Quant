"""自选股相关 schema。ponytail: 不做复杂字段，能 get/post/delete 就够。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    note: Optional[str] = None
    sort_order: int
    added_at: datetime


class WatchlistItemCreate(BaseModel):
    """添加自选股请求 body。"""

    symbol: str = Field(..., min_length=1, max_length=32, description="股票代码，如 sh600519")
    note: Optional[str] = Field(default=None, max_length=255)
