from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.repositories._base import BaseRepository

from backend.app.models import IngestBatch, SyncTask
from backend.app.models.entities import utcnow


class IngestBatchRepository(BaseRepository):

    def create_batch(
        self,
        *,
        task: SyncTask,
        dataset_name: str,
        source: str,
        requested_source: str,
        raw_records: int,
        normalized_records: int,
        validation_errors: list[str],
        dropped_records: int | None = None,
        market: str | None = None,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        raw_artifact_id: int | None = None,
        schema_version: str = "v1",
        normalize_version: str = "v1",
    ) -> IngestBatch:
        if raw_records < 0 or normalized_records < 0:
            raise ValueError("raw_records and normalized_records must be non-negative.")
        if normalized_records > raw_records:
            raise ValueError("normalized_records cannot exceed raw_records.")
        if dropped_records is not None and dropped_records != raw_records - normalized_records:
            raise ValueError("dropped_records must equal raw_records - normalized_records.")
        effective_validation_errors = list(validation_errors)
        if raw_records > 0 and normalized_records == 0:
            effective_validation_errors.append("All raw records were dropped during normalization.")
        batch = IngestBatch(
            task_id=task.id,
            dataset_name=dataset_name,
            source=source,
            requested_source=requested_source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            raw_artifact_id=raw_artifact_id,
            schema_version=schema_version,
            normalize_version=normalize_version,
            raw_records=raw_records,
            normalized_records=normalized_records,
            dropped_records=raw_records - normalized_records if dropped_records is None else dropped_records,
            validation_errors_json=effective_validation_errors,
            status="validated" if not effective_validation_errors else "failed",
            quality_status="pending" if not effective_validation_errors else "failed",
            error_message="; ".join(effective_validation_errors) if effective_validation_errors else None,
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def complete_batch(self, batch: IngestBatch, *, records_written: int, quality_status: str = "good") -> None:
        if batch.status == "failed":
            raise RuntimeError(batch.error_message or "Cannot complete a failed ingest batch.")
        batch.status = "success"
        batch.records_written = records_written
        batch.quality_status = quality_status
        batch.finished_at = utcnow()
        self.db.flush()

    def fail_batch(self, batch: IngestBatch, *, message: str) -> None:
        batch.status = "failed"
        batch.error_message = message
        batch.quality_status = "failed"
        batch.finished_at = utcnow()
        self.db.flush()

    def mark_reconcile_required(self, batch: IngestBatch, *, message: str) -> None:
        batch.status = "reconcile_required"
        batch.error_message = message
        batch.quality_status = "unknown"
        batch.finished_at = utcnow()
        self.db.flush()

    def list_for_task(self, task_id: int) -> list[IngestBatch]:
        return list(
            self.db.scalars(
                select(IngestBatch)
                .where(IngestBatch.task_id == task_id)
                .order_by(IngestBatch.started_at.asc(), IngestBatch.id.asc())
            ).all()
        )
