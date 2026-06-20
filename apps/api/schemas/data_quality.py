from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DataQualityReportTrace(BaseModel):
    dataset_source: str | None = None
    storage_type: str | None = None
    row_count: int | None = None
    latest_data_date: date | None = None
    quality_status: str | None = None
    schema_fields_count: int | None = None
    primary_keys_json: list[str] = Field(default_factory=list)
    partition_keys_json: list[str] = Field(default_factory=list)
    latest_batch_id: int | None = None
    latest_task_id: int | None = None
    latest_batch_source: str | None = None
    latest_batch_requested_source: str | None = None
    latest_batch_market: str | None = None
    latest_batch_symbol: str | None = None
    latest_batch_start_date: date | None = None
    latest_batch_end_date: date | None = None
    latest_batch_status: str | None = None
    latest_batch_schema_version: str | None = None
    latest_batch_normalize_version: str | None = None
    latest_batch_records_written: int | None = None
    latest_batch_quality_status: str | None = None
    latest_batch_finished_at: datetime | None = None


class DataQualityReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_name: str
    check_type: str
    status: str
    severity: str
    metric_name: str
    metric_value: str | None
    expected_value: str | None
    message: str
    checked_at: datetime
    trace: DataQualityReportTrace | None = None


class PaginatedDataQualityReports(BaseModel):
    items: list[DataQualityReportRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    checked_at: datetime | None = None


class DataQualityCheckRunRead(BaseModel):
    checked_at: datetime
    reports_total: int
    reports_warning: int
    reports_error: int


class DataQualityCheckRunList(BaseModel):
    items: list[DataQualityCheckRunRead]


class DataQualityOverview(BaseModel):
    datasets_total: int
    datasets_good: int
    datasets_warning: int
    datasets_error: int
    datasets_unknown: int
    reports_total: int
    reports_warning: int
    reports_error: int
    latest_checked_at: datetime | None


class DataQualityCheckResult(BaseModel):
    checked_datasets: int
    reports_created: int
    checked_at: datetime
    overview: DataQualityOverview
