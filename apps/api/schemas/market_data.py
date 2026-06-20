from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DailyBarsSyncRequest(BaseModel):
    source: str = Field(default="auto", min_length=1)
    market: str = Field(default="A_SHARE", min_length=1)
    symbol: str = Field(min_length=1)
    start_date: date
    end_date: date


class DailyBarsMarketRepairRequest(BaseModel):
    source: str = Field(default="auto", min_length=1)
    market: str = Field(default="A_SHARE", min_length=1)
    start_date: date
    end_date: date
    max_symbols: int = Field(default=20, ge=1, le=200)


class DailyBarsMarketRepairPreviewItem(BaseModel):
    symbol: str
    exchange: str
    name: str
    start_date: date
    end_date: date
    missing_trade_days: int


class DailyBarsMarketRepairPreviewResponse(BaseModel):
    source: str
    selected_source: str
    candidate_sources: list[str]
    market: str
    start_date: date
    end_date: date
    max_symbols: int
    stock_pool_count: int
    open_dates_count: int
    planned_symbols: int
    planned_missing_symbol_days: int
    supported_exchanges: list[str] | None
    sample_items: list[DailyBarsMarketRepairPreviewItem]
    message: str


class DailyBarRead(BaseModel):
    symbol: str
    exchange: str
    market: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float | None
    volume: float
    amount: float
    adjust_factor: float | None
    adjust_type: str
    source: str
    ingested_at: datetime


class PaginatedDailyBars(BaseModel):
    items: list[DailyBarRead]
    total: int
    page: int
    page_size: int
    total_pages: int
