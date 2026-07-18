from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _extract_task_source_selection(value: Any) -> tuple[list[str] | None, str | None]:
    logs = None
    if isinstance(value, dict):
        logs = value.get("logs")
    else:
        logs = getattr(value, "logs", None)

    candidate_sources: list[str] | None = None
    selected_source: str | None = None

    if not logs:
        return None, None

    for log in logs:
        payload = log.get("payload_json") if isinstance(log, dict) else getattr(log, "payload_json", None)
        if not isinstance(payload, dict):
            continue

        if candidate_sources is None:
            raw_candidates = payload.get("candidate_sources")
            if isinstance(raw_candidates, list):
                normalized_candidates = [item for item in raw_candidates if isinstance(item, str) and item]
                if normalized_candidates:
                    candidate_sources = normalized_candidates

        if selected_source is None:
            raw_selected = payload.get("selected_source")
            if isinstance(raw_selected, str) and raw_selected:
                selected_source = raw_selected

        if candidate_sources is not None and selected_source is not None:
            break

    return candidate_sources, selected_source


def _task_field_value(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name)


class SyncTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_type: str
    source: str
    market: str | None
    symbol: str | None
    start_date: date | None
    end_date: date | None
    max_symbols: int | None = None
    start_policy: str | None = None
    adjust_type: str | None = None
    status: str
    progress: int
    records_read: int
    records_written: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    candidate_sources: list[str] | None = None
    selected_source: str | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_source_selection(cls, value: Any) -> Any:
        if isinstance(value, dict) and "candidate_sources" in value and "selected_source" in value:
            return value

        candidate_sources, selected_source = _extract_task_source_selection(value)
        payload = {
            "id": _task_field_value(value, "id"),
            "task_type": _task_field_value(value, "task_type"),
            "source": _task_field_value(value, "source"),
            "market": _task_field_value(value, "market"),
            "symbol": _task_field_value(value, "symbol"),
            "start_date": _task_field_value(value, "start_date"),
            "end_date": _task_field_value(value, "end_date"),
            "max_symbols": _task_field_value(value, "max_symbols"),
            "start_policy": _task_field_value(value, "start_policy"),
            "adjust_type": _task_field_value(value, "adjust_type"),
            "status": _task_field_value(value, "status"),
            "progress": _task_field_value(value, "progress"),
            "records_read": _task_field_value(value, "records_read"),
            "records_written": _task_field_value(value, "records_written"),
            "error_message": _task_field_value(value, "error_message"),
            "started_at": _task_field_value(value, "started_at"),
            "finished_at": _task_field_value(value, "finished_at"),
            "created_at": _task_field_value(value, "created_at"),
            "candidate_sources": candidate_sources,
            "selected_source": selected_source,
        }
        if isinstance(value, dict):
            return {**value, **payload}
        return payload


class SyncTaskLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    level: str
    message: str
    payload_json: dict | None
    created_at: datetime


class IngestBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    raw_records: int
    normalized_records: int
    dropped_records: int
    records_written: int
    validation_errors_json: list[str]
    error_message: str | None
    quality_status: str
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


class PaginatedSyncTasks(BaseModel):
    items: list[SyncTaskRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class SyncScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    task_type: str
    source: str
    market: str | None
    symbol: str | None
    cron_expression: str
    enabled: bool
    schedule_note: str
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SyncScheduleUpdate(BaseModel):
    enabled: bool | None = None
    cron_expression: str | None = Field(default=None, min_length=1, max_length=128)
    source: str | None = Field(default=None, min_length=1, max_length=64)
    market: str | None = Field(default=None, min_length=1, max_length=32)
    symbol: str | None = Field(default=None, max_length=32)


class SyncSchedulesRead(BaseModel):
    items: list[SyncScheduleRead]
    total: int


class SyncRunnerTaskRefRead(BaseModel):
    id: int | None
    task_type: str | None
    status: str | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


class SyncRunnerStatusRead(BaseModel):
    mode: str
    status: str
    message: str
    worker_command: str
    worker_note: str
    supported_task_types: list[str]
    pending_count: int
    running_count: int
    failed_count: int
    success_count: int
    enabled_schedules: int
    total_schedules: int
    latest_task_id: int | None
    latest_task_status: str | None
    latest_task_created_at: datetime | None
    latest_triggered_at: datetime | None
    current_task: SyncRunnerTaskRefRead
    next_pending_task: SyncRunnerTaskRefRead
    latest_success_task: SyncRunnerTaskRefRead
    latest_failed_task: SyncRunnerTaskRefRead
    latest_worker_activity_at: datetime | None


class SyncTaskLogsRead(BaseModel):
    task_id: int
    items: list[SyncTaskLogRead]
    total: int


class SyncTaskIngestBatchesRead(BaseModel):
    task_id: int
    items: list[IngestBatchRead]
    total: int
