from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.db.session import SessionLocal
from backend.app.models import Dataset, DatasetVersion
from backend.app.repositories.dataset_versions import DatasetVersionRepository
from backend.app.services.dataset_manifest import DatasetManifestStore


def _manifest(*, close_checksum: str = "b" * 64) -> dict:
    return {
        "manifest_version": "v1",
        "dataset": "daily_bars",
        "dataset_version_id": "daily-bars-content-v1",
        "schema_version": "v1",
        "normalize_version": "v1",
        "schema_sha256": "a" * 64,
        "adjust_type": "none",
        "primary_keys": ["symbol", "exchange", "market", "trade_date", "adjust_type"],
        "partition_keys": ["market", "trade_date"],
        "row_count": 2,
        "min_trade_date": "2026-07-18",
        "max_trade_date": "2026-07-18",
        "quality": {"status": "good", "policy": "daily-bars-v1"},
        "lineage": {"ingest_batch_ids": [1], "raw_artifact_ids": [2]},
        "partitions": [
            {
                "key": {"market": "A_SHARE", "trade_date": "2026-07-18"},
                "uri": "versions/daily_bars/v1/market=A_SHARE/trade_date=2026-07-18/part-000.parquet",
                "sha256": close_checksum,
                "byte_size": 100,
                "row_count": 2,
                "min_trade_date": "2026-07-18",
                "max_trade_date": "2026-07-18",
            }
        ],
    }


def test_dataset_version_repository_registers_candidate_with_partitions(client, tmp_path):
    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        manifest = _manifest()
        artifact = DatasetManifestStore(tmp_path / "lake").write(manifest)
        version, created = DatasetVersionRepository(db).create_candidate(
            dataset=dataset, manifest=manifest, manifest_artifact=artifact
        )
        db.commit()

        assert created is True
        assert version.status == "candidate"
        assert version.version_seq == 1
        assert version.version_key == artifact.sha256
        assert version.manifest_sha256 == artifact.sha256
        assert version.manifest_uri == artifact.relative_uri
        assert version.row_count == 2
        assert version.quality_status == "good"
        assert len(version.partitions) == 1
        assert version.partitions[0].relative_uri.endswith("part-000.parquet")
        assert version.partitions[0].sha256 == "b" * 64
        assert version.partitions[0].row_count == 2
    finally:
        db.close()


def test_dataset_version_repository_reuses_same_manifest_and_increments_changed_version(client, tmp_path):
    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        repository = DatasetVersionRepository(db)
        store = DatasetManifestStore(tmp_path / "lake")

        first_manifest = _manifest()
        first_artifact = store.write(first_manifest)
        first, first_created = repository.create_candidate(
            dataset=dataset, manifest=first_manifest, manifest_artifact=first_artifact
        )
        db.commit()

        repeated, repeated_created = repository.create_candidate(
            dataset=dataset, manifest=first_manifest, manifest_artifact=first_artifact
        )
        assert repeated.id == first.id
        assert repeated_created is False

        changed_manifest = _manifest(close_checksum="c" * 64)
        changed_artifact = store.write(changed_manifest)
        changed, changed_created = repository.create_candidate(
            dataset=dataset, manifest=changed_manifest, manifest_artifact=changed_artifact
        )
        db.commit()

        assert changed_created is True
        assert changed.id != first.id
        assert changed.version_seq == 2
        assert db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id).count() == 2
    finally:
        db.close()


def test_dataset_with_registered_version_cannot_be_deleted(client, tmp_path):
    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        manifest = _manifest()
        artifact = DatasetManifestStore(tmp_path / "lake").write(manifest)
        DatasetVersionRepository(db).create_candidate(dataset=dataset, manifest=manifest, manifest_artifact=artifact)
        db.commit()

        db.delete(dataset)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        assert db.query(DatasetVersion).count() == 1
    finally:
        db.close()


def test_dataset_version_moves_candidate_to_ready_then_published(client, tmp_path):
    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        manifest = _manifest()
        artifact = DatasetManifestStore(tmp_path / "lake").write(manifest)
        version, _ = DatasetVersionRepository(db).create_candidate(
            dataset=dataset, manifest=manifest, manifest_artifact=artifact
        )
        repository = DatasetVersionRepository(db)

        ready = repository.mark_ready(version)
        assert ready.status == "ready"
        published = repository.publish(version)
        db.commit()

        assert published.status == "published"
        assert published.published_at is not None
    finally:
        db.close()


def test_dataset_version_quality_failure_cannot_become_ready(client, tmp_path):
    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        manifest = _manifest()
        manifest["quality"]["status"] = "error"
        artifact = DatasetManifestStore(tmp_path / "lake").write(manifest)
        version, _ = DatasetVersionRepository(db).create_candidate(
            dataset=dataset, manifest=manifest, manifest_artifact=artifact
        )

        with pytest.raises(ValueError, match="quality"):
            DatasetVersionRepository(db).mark_ready(version)
        assert version.status == "candidate"
    finally:
        db.close()


def test_dataset_version_cannot_publish_before_ready_or_publish_twice(client, tmp_path):
    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        manifest = _manifest()
        artifact = DatasetManifestStore(tmp_path / "lake").write(manifest)
        version, _ = DatasetVersionRepository(db).create_candidate(
            dataset=dataset, manifest=manifest, manifest_artifact=artifact
        )
        repository = DatasetVersionRepository(db)

        with pytest.raises(ValueError, match="ready"):
            repository.publish(version)
        repository.mark_ready(version)
        repository.publish(version)
        with pytest.raises(ValueError, match="published"):
            repository.publish(version)
    finally:
        db.close()
