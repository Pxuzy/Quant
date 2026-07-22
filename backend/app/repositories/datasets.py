from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Dataset
from backend.app.repositories._base import BaseRepository

STOCK_SCHEMA = {
    "symbol": "string",
    "exchange": "string",
    "market": "string",
    "name": "string",
    "status": "string",
    "industry": "string",
    "listing_date": "date",
    "delisting_date": "date",
    "source": "string",
}

DAILY_BAR_SCHEMA = {
    "symbol": "string",
    "exchange": "string",
    "market": "string",
    "trade_date": "date",
    "open": "float",
    "high": "float",
    "low": "float",
    "close": "float",
    "pre_close": "float",
    "volume": "float",
    "amount": "float",
    "adjust_factor": "float",
    "adjust_type": "string",
    "source": "string",
    "ingested_at": "datetime",
}

TRADING_CALENDAR_SCHEMA = {
    "market": "string",
    "trade_date": "date",
    "is_open": "bool",
    "source": "string",
}


class DatasetRepository(BaseRepository):

    def upsert_stock_dataset(self, *, source: str, row_count: int, latest_data_date: date) -> Dataset:
        dataset = self.db.scalar(select(Dataset).where(Dataset.name == "stocks"))
        if dataset is None:
            dataset = Dataset(
                name="stocks",
                layer="silver",
                storage_type="postgres",
                schema_json=STOCK_SCHEMA,
                primary_keys_json=["symbol", "exchange", "market"],
                partition_keys_json=["market"],
                source=source,
            )
            self.db.add(dataset)

        dataset.source = source
        dataset.row_count = row_count
        dataset.latest_data_date = latest_data_date
        dataset.quality_status = "good" if row_count > 0 else "warning"
        self.db.flush()
        return dataset

    def upsert_daily_bars_dataset(
        self,
        *,
        source: str,
        row_count: int,
        latest_data_date: date | None,
        path: str,
    ) -> Dataset:
        dataset = self.db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        if dataset is None:
            dataset = Dataset(
                name="daily_bars",
                layer="silver",
                storage_type="parquet",
                schema_json=DAILY_BAR_SCHEMA,
                primary_keys_json=["symbol", "exchange", "market", "trade_date", "adjust_type"],
                partition_keys_json=["market", "trade_date"],
                source=source,
            )
            self.db.add(dataset)

        dataset.source = source
        dataset.path = path
        dataset.row_count = row_count
        dataset.latest_data_date = latest_data_date
        dataset.quality_status = "good" if row_count > 0 else "warning"
        self.db.flush()
        return dataset

    def upsert_trading_calendar_dataset(
        self,
        *,
        source: str,
        row_count: int,
        latest_data_date: date | None,
    ) -> Dataset:
        dataset = self.db.scalar(select(Dataset).where(Dataset.name == "trading_calendars"))
        if dataset is None:
            dataset = Dataset(
                name="trading_calendars",
                layer="silver",
                storage_type="postgres",
                schema_json=TRADING_CALENDAR_SCHEMA,
                primary_keys_json=["market", "trade_date"],
                partition_keys_json=["market"],
                source=source,
            )
            self.db.add(dataset)

        dataset.source = source
        dataset.row_count = row_count
        dataset.latest_data_date = latest_data_date
        dataset.quality_status = "good" if row_count > 0 else "warning"
        self.db.flush()
        return dataset
