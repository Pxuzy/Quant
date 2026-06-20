from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class TradingCalendarSyncRequest(BaseModel):
    source: str = Field(default="auto", min_length=1)
    market: str = Field(default="A_SHARE", min_length=1)
    start_date: date
    end_date: date


class TradingCalendarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market: str
    trade_date: date
    is_open: bool
    source: str
    updated_at: datetime


class PaginatedTradingCalendars(BaseModel):
    items: list[TradingCalendarRead]
    total: int
    page: int
    page_size: int
    total_pages: int
