from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.models import Dataset, IngestBatch
from apps.api.repositories.daily_bars import DailyBarRepository


BAR_READER_CONTRACT = {
    "name": "BarReader",
    "dataset": "daily_bars",
    "layer": "silver",
    "adjust_type": "none",
    "source_policy": "governed_only",
}


class ResearchDataService:
    def __init__(self, db: Session | None = None, *, lake_root: str | Path | None = None) -> None:
        self.db = db
        self.daily_bar_repo = DailyBarRepository(lake_root=lake_root)

    def read_bars(
        self,
        *,
        symbol: str,
        market: str,
        start_date: date,
        end_date: date,
        page: int = 1,
        page_size: int = 5000,
    ) -> dict:
        symbol_code = symbol.strip()
        market_code = market.strip().upper()
        if not symbol_code:
            raise ValueError("symbol is required.")
        if not market_code:
            raise ValueError("market is required.")
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date.")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1.")
        if page_size < 1 or page_size > 10000:
            raise ValueError("page_size must be between 1 and 10000.")

        items, total = self.daily_bar_repo.list_daily_bars(
            symbol=symbol_code,
            market=market_code,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            sort_order="asc",
        )
        return {
            "contract": self._bar_reader_contract(),
            "symbol": symbol_code,
            "market": market_code,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "page_size": page_size,
            "items": items,
            "total": total,
        }

    def _bar_reader_contract(self) -> dict:
        return {
            **BAR_READER_CONTRACT,
            "manifest": self._daily_bars_manifest(),
        }

    def _daily_bars_manifest(self) -> dict:
        if self.db is None:
            return {
                "dataset_name": "daily_bars",
                "layer": "silver",
                "storage_type": "parquet",
                "source": "unknown",
                "row_count": 0,
                "latest_data_date": None,
                "quality_status": "unknown",
                "updated_at": None,
                "latest_ingest_batch": None,
            }

        dataset = self.db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        if dataset is None:
            return {
                "dataset_name": "daily_bars",
                "layer": "silver",
                "storage_type": "parquet",
                "source": "unknown",
                "row_count": 0,
                "latest_data_date": None,
                "quality_status": "missing",
                "updated_at": None,
                "latest_ingest_batch": None,
            }

        return {
            "dataset_name": dataset.name,
            "layer": dataset.layer,
            "storage_type": dataset.storage_type,
            "source": dataset.source,
            "row_count": dataset.row_count,
            "latest_data_date": dataset.latest_data_date,
            "quality_status": dataset.quality_status,
            "updated_at": dataset.updated_at,
            "latest_ingest_batch": self._latest_daily_bars_ingest_batch(),
        }

    def _latest_daily_bars_ingest_batch(self) -> dict | None:
        if self.db is None:
            return None

        batch = self.db.scalar(
            select(IngestBatch)
            .where(IngestBatch.dataset_name == "daily_bars", IngestBatch.status == "success")
            .order_by(func.coalesce(IngestBatch.finished_at, IngestBatch.started_at).desc(), IngestBatch.id.desc())
            .limit(1)
        )
        if batch is None:
            return None

        return {
            "id": batch.id,
            "task_id": batch.task_id,
            "source": batch.source,
            "requested_source": batch.requested_source,
            "market": batch.market,
            "symbol": batch.symbol,
            "start_date": batch.start_date,
            "end_date": batch.end_date,
            "status": batch.status,
            "schema_version": batch.schema_version,
            "normalize_version": batch.normalize_version,
            "records_written": batch.records_written,
            "quality_status": batch.quality_status,
        }
