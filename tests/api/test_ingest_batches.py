from __future__ import annotations

import pytest

from backend.app.db.session import SessionLocal
from backend.app.models import SyncTask
from backend.app.repositories.ingest_batches import IngestBatchRepository


def test_ingest_batch_persists_explicit_dropped_record_count(client):
    db = SessionLocal()
    try:
        task = SyncTask(task_type="stock_list", source="fixture", market="A_SHARE")
        db.add(task)
        db.commit()
        db.refresh(task)

        batch = IngestBatchRepository(db).create_batch(
            task=task,
            dataset_name="stocks",
            source="fixture",
            requested_source="fixture",
            market="A_SHARE",
            raw_records=7,
            normalized_records=2,
            dropped_records=5,
            validation_errors=[],
        )
        db.commit()
        db.refresh(batch)
    finally:
        db.close()

    assert batch.raw_records == 7
    assert batch.normalized_records == 2
    assert batch.dropped_records == 5


def test_ingest_batch_rejects_inconsistent_normalization_counts(client):
    db = SessionLocal()
    try:
        task = SyncTask(task_type="stock_list", source="fixture", market="A_SHARE")
        db.add(task)
        db.commit()
        db.refresh(task)

        with pytest.raises(ValueError, match="cannot exceed"):
            IngestBatchRepository(db).create_batch(
                task=task,
                dataset_name="stocks",
                source="fixture",
                requested_source="fixture",
                market="A_SHARE",
                raw_records=1,
                normalized_records=2,
                validation_errors=[],
            )
        with pytest.raises(ValueError, match="must equal"):
            IngestBatchRepository(db).create_batch(
                task=task,
                dataset_name="stocks",
                source="fixture",
                requested_source="fixture",
                market="A_SHARE",
                raw_records=2,
                normalized_records=1,
                dropped_records=0,
                validation_errors=[],
            )
    finally:
        db.close()
