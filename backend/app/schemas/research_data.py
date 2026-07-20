from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from backend.app.schemas.market_data import DailyBarRead


class ResearchIngestBatchRead(BaseModel):
    id: int
    task_id: int
    source: str
    requested_source: str
    market: str | None
    symbol: str | None
    start_date: date | None
    end_date: date | None
    status: str
    schema_version: str
    normalize_version: str
    records_written: int
    quality_status: str


class ResearchDataManifestRead(BaseModel):
    dataset_name: str
    layer: str
    storage_type: str
    source: str
    row_count: int
    latest_data_date: date | None
    quality_status: str
    updated_at: datetime | None
    latest_ingest_batch: ResearchIngestBatchRead | None
    dataset_version_id: int | None = None
    manifest_uri: str | None = None
    manifest_sha256: str | None = None
    bundle_key: str | None = None


class ResearchDataContractRead(BaseModel):
    name: str
    dataset: str
    layer: str
    adjust_type: str
    source_policy: str
    snapshot_id: int | None = None
    dataset_version_id: int | None = None
    manifest_sha256: str | None = None
    manifest: ResearchDataManifestRead


class ResearchBarsRead(BaseModel):
    contract: ResearchDataContractRead
    symbol: str
    market: str
    start_date: date
    end_date: date
    page: int
    page_size: int
    items: list[DailyBarRead]
    total: int
