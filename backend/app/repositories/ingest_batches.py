from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import IngestBatch, SyncTask
from backend.app.models.entities import utcnow


class IngestBatchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

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
        market: str | None = None,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        raw_artifact_id: int | None = None,
        schema_version: str = "v1",
        normalize_version: str = "v1",
    ) -> IngestBatch:
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
            validation_errors_json=validation_errors,
            status="validated" if not validation_errors else "failed",
            quality_status="pending" if not validation_errors else "failed",
            error_message="; ".join(validation_errors) if validation_errors else None,
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def complete_batch(self, batch: IngestBatch, *, records_written: int, quality_status: str = "good") -> None:
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

    def list_for_task(self, task_id: int) -> list[IngestBatch]:
        return list(
            self.db.scalars(
                select(IngestBatch)
                .where(IngestBatch.task_id == task_id)
                .order_by(IngestBatch.started_at.asc(), IngestBatch.id.asc())
            ).all()
        )
