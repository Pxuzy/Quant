from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import SessionLocal
from backend.app.models import RawArtifact, SyncTask
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


def test_sqlite_raw_artifact_foreign_keys_restrict_invalid_references_and_deletes(client):
    db = SessionLocal()
    try:
        assert db.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        task = SyncTask(task_type="daily_bars", source="fixture", market="A_SHARE")
        db.add(task)
        db.commit()
        db.refresh(task)

        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE sync_tasks SET input_raw_artifact_id = :artifact_id WHERE id = :task_id"),
                {"artifact_id": 999999, "task_id": task.id},
            )
            db.commit()
        db.rollback()

        artifact = RawArtifact(
            task_id=task.id,
            dataset_name="daily_bars",
            source="fixture",
            requested_source="fixture",
            market="A_SHARE",
            symbol="600519",
            uri="/tmp/artifact.json",
            sha256="0" * 64,
            byte_size=2,
            row_count=0,
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        db.execute(
            text("UPDATE sync_tasks SET input_raw_artifact_id = :artifact_id WHERE id = :task_id"),
            {"artifact_id": artifact.id, "task_id": task.id},
        )
        db.commit()

        with pytest.raises(IntegrityError):
            db.delete(artifact)
            db.commit()
        db.rollback()
    finally:
        db.close()
