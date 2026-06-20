from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class DatabaseStatusRead(BaseModel):
    database_kind: str
    database_role: str
    database_note: str
    database_url: str
    database_size_bytes: int | None
    data_lake_path: str
    data_lake_size_bytes: int
    parquet_file_count: int
    total_file_count: int
    duckdb_engine_status: str
    duckdb_engine_note: str


class DatasetSnapshotRead(BaseModel):
    dataset_name: str
    layer: str
    storage_type: str
    source: str
    row_count: int
    latest_data_date: date | None
    quality_status: str
    dataset_version: str
    schema_fields_count: int
    primary_keys_json: list[str]
    partition_keys_json: list[str]
    updated_at: datetime


class SyncWatermarkRead(BaseModel):
    dataset_name: str
    source: str
    requested_source: str
    market: str | None
    symbol: str | None
    latest_success_date: date | None
    last_success_at: datetime | None
    records_written: int
    quality_status: str
    task_id: int
    batch_id: int
    last_failed_at: datetime | None = None
    last_failure_reason: str | None = None
    last_failure_task_id: int | None = None
    last_failure_batch_id: int | None = None
    repair_start_date: date | None = None
    repair_end_date: date | None = None
    repair_reason: str | None = None


class ProviderIntegrationRead(BaseModel):
    source: str
    attempts: int
    successes: int
    failures: int
    fallback_successes: int
    records_written: int
    last_success_at: datetime | None
    last_failure_at: datetime | None


class RecentIngestBatchRead(BaseModel):
    id: int
    task_id: int
    dataset_name: str
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
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class DatabaseLineageItemRead(BaseModel):
    id: int
    task_id: int
    task_type: str
    task_status: str
    task_source: str
    task_error_message: str | None
    dataset_name: str
    source: str
    requested_source: str
    market: str | None
    symbol: str | None
    start_date: date | None
    end_date: date | None
    status: str
    schema_version: str
    normalize_version: str
    raw_records: int
    normalized_records: int
    records_written: int
    validation_errors_json: list[str]
    error_message: str | None
    quality_status: str
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


class DatabaseLineageRead(BaseModel):
    items: list[DatabaseLineageItemRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class DatabaseCoverageSummaryRead(BaseModel):
    market: str
    coverage_status: str
    coverage_message: str | None = None
    stock_pool_total: int
    daily_covered_stock_count: int
    calendar_latest_date: date | None
    coverage_start_date: date | None
    coverage_end_date: date | None
    daily_expected_symbol_days: int
    daily_actual_symbol_days: int
    daily_missing_symbol_days: int
    daily_completeness: float | None


class DatabaseIntegrationSummaryRead(BaseModel):
    datasets_total: int
    total_rows: int
    latest_data_date: date | None
    recent_batches_total: int
    failed_batches_total: int
    fallback_successes_total: int
    healthy_providers_total: int


class DatabaseIntegrationOverviewRead(BaseModel):
    summary: DatabaseIntegrationSummaryRead
    coverage_summary: DatabaseCoverageSummaryRead
    dataset_snapshots: list[DatasetSnapshotRead]
    sync_watermarks: list[SyncWatermarkRead]
    provider_integrations: list[ProviderIntegrationRead]
    recent_batches: list[RecentIngestBatchRead]
