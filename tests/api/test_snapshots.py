from __future__ import annotations

from datetime import date

import pytest

from backend.app.db.session import SessionLocal
from backend.app.models import Dataset, DatasetVersion, DatasetVersionPartition
from backend.app.repositories.snapshots import SnapshotRepository


def _published_version(
    db,
    *,
    dataset_name: str,
    version_seq: int = 1,
    dataset: Dataset | None = None,
    adjust_type: str = "none",
) -> tuple[Dataset, DatasetVersion]:
    if dataset is None:
        dataset = Dataset(name=dataset_name, layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.flush()
    version = DatasetVersion(
        dataset_id=dataset.id,
        version_seq=version_seq,
        version_key=f"{version_seq:064d}",
        status="published",
        schema_version="v1",
        normalize_version="v1",
        schema_sha256="a" * 64,
        adjust_type=adjust_type,
        quality_status="good",
        row_count=1,
        min_trade_date=date(2026, 7, 18),
        max_trade_date=date(2026, 7, 18),
        manifest_uri=f"versions/{dataset_name}/manifest.json",
        manifest_sha256=f"{version_seq + 1:064d}",
    )
    version.partitions = [
        DatasetVersionPartition(
            partition_spec_json={"market": "A_SHARE", "trade_date": "2026-07-18"},
            relative_uri=f"versions/{dataset_name}/part.parquet",
            sha256="b" * 64,
            byte_size=10,
            row_count=1,
            status="sealed",
        )
    ]
    db.add(version)
    db.flush()
    return dataset, version


def test_snapshot_can_activate_only_published_version(client):
    db = SessionLocal()
    try:
        dataset, version = _published_version(db, dataset_name="daily_bars")
        repository = SnapshotRepository(db)
        snapshot = repository.create_draft(name="research-2026-07-18")
        repository.add_member(snapshot, dataset=dataset, version=version, role="bars")

        activated = repository.activate(snapshot)
        db.commit()

        assert activated.status == "active"
        assert activated.activated_at is not None
        assert len(activated.members) == 1
        assert activated.members[0].role == "bars"
    finally:
        db.close()


def test_snapshot_rejects_unpublished_version_and_empty_activation(client):
    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.flush()
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_seq=1,
            version_key="1" * 64,
            status="candidate",
            schema_version="v1",
            normalize_version="v1",
            schema_sha256="a" * 64,
            adjust_type="none",
            quality_status="good",
            row_count=0,
            manifest_uri="versions/daily_bars/manifest.json",
            manifest_sha256="2" * 64,
        )
        db.add(version)
        db.flush()
        repository = SnapshotRepository(db)
        snapshot = repository.create_draft(name="invalid")

        with pytest.raises(ValueError, match="published"):
            repository.add_member(snapshot, dataset=dataset, version=version, role="bars")
        with pytest.raises(ValueError, match="member"):
            repository.activate(snapshot)
    finally:
        db.close()


def test_activating_new_snapshot_retires_previous_active_snapshot(client):
    db = SessionLocal()
    try:
        dataset, version = _published_version(db, dataset_name="daily_bars")
        repository = SnapshotRepository(db)
        first = repository.create_draft(name="first")
        repository.add_member(first, dataset=dataset, version=version, role="bars")
        repository.activate(first)
        db.commit()

        second = repository.create_draft(name="second")
        repository.add_member(second, dataset=dataset, version=version, role="bars")
        repository.activate(second)
        db.commit()

        assert first.status == "retired"
        assert second.status == "active"
        assert repository.count_active() == 1
    finally:
        db.close()


def test_snapshot_accepts_three_adjustment_versions_of_same_dataset(client):
    db = SessionLocal()
    try:
        dataset, none_version = _published_version(
            db,
            dataset_name="daily_bars",
            version_seq=1,
            adjust_type="none",
        )
        _, qfq_version = _published_version(
            db,
            dataset_name="daily_bars",
            version_seq=2,
            dataset=dataset,
            adjust_type="qfq",
        )
        _, hfq_version = _published_version(
            db,
            dataset_name="daily_bars",
            version_seq=3,
            dataset=dataset,
            adjust_type="hfq",
        )
        repository = SnapshotRepository(db)
        snapshot = repository.create_draft(name="all-adjustments")

        repository.add_member(snapshot, dataset=dataset, version=none_version, role="bars-none")
        repository.add_member(snapshot, dataset=dataset, version=qfq_version, role="bars-qfq")
        repository.add_member(snapshot, dataset=dataset, version=hfq_version, role="bars-hfq")
        repository.activate(snapshot)
        db.commit()

        assert snapshot.status == "active"
        assert {member.role for member in snapshot.members} == {
            "bars-none",
            "bars-qfq",
            "bars-hfq",
        }
    finally:
        db.close()


def test_snapshot_rejects_role_adjustment_mismatch(client):
    db = SessionLocal()
    try:
        dataset, version = _published_version(
            db,
            dataset_name="daily_bars",
            adjust_type="qfq",
        )
        repository = SnapshotRepository(db)
        snapshot = repository.create_draft(name="mismatched-adjustment")

        with pytest.raises(ValueError, match="adjust_type=none"):
            repository.add_member(snapshot, dataset=dataset, version=version, role="bars-none")
    finally:
        db.close()


def test_snapshot_rejects_duplicate_role(client):
    db = SessionLocal()
    try:
        dataset, version = _published_version(db, dataset_name="daily_bars")
        repository = SnapshotRepository(db)
        snapshot = repository.create_draft(name="duplicate-role")
        repository.add_member(snapshot, dataset=dataset, version=version, role="bars-none")

        with pytest.raises(Exception, match="uq_snapshot_role|UNIQUE constraint failed"):
            repository.add_member(snapshot, dataset=dataset, version=version, role="bars-none")
    finally:
        db.rollback()
        db.close()


def test_active_snapshot_cannot_be_modified(client):
    db = SessionLocal()
    try:
        dataset, version = _published_version(db, dataset_name="daily_bars")
        repository = SnapshotRepository(db)
        snapshot = repository.create_draft(name="immutable")
        repository.add_member(snapshot, dataset=dataset, version=version, role="bars")
        repository.activate(snapshot)

        with pytest.raises(ValueError, match="active"):
            repository.add_member(snapshot, dataset=dataset, version=version, role="calendar")
    finally:
        db.close()
