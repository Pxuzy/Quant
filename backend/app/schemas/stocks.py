from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.sync_tasks import IngestBatchRead


class StockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    exchange: str
    market: str
    name: str
    status: str
    industry: str | None
    listing_date: date | None
    delisting_date: date | None
    source: str
    latest_data_date: date | None = None
    data_completeness: float | None = None
    created_at: datetime
    updated_at: datetime


class PaginatedStocks(BaseModel):
    items: list[StockRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class StockDailyCoverageRead(BaseModel):
    symbol: str
    market: str
    first_data_date: date | None
    latest_data_date: date | None
    expected_trade_days: int
    actual_trade_days: int
    missing_trade_days: int
    data_completeness: float | None
    missing_trade_date_samples: list[date]


class StockDailyQualityRead(BaseModel):
    symbol: str
    market: str
    status: str
    checked_rows: int
    first_data_date: date | None
    latest_data_date: date | None
    expected_trade_days: int
    actual_trade_days: int
    missing_trade_days: int
    data_completeness: float | None
    missing_trade_date_samples: list[date]
    duplicate_daily_keys: int
    ohlc_error_count: int
    negative_price_count: int
    negative_volume_count: int
    negative_amount_count: int
    adjust_types: list[str]
    sources: list[str]


class StockDailyIngestBatchesRead(BaseModel):
    symbol: str
    market: str
    items: list[IngestBatchRead]
    total: int


class StockSyncRequest(BaseModel):
    source: str = Field(default="auto", min_length=1)
    market: str = Field(default="A_SHARE", min_length=1)
