from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

from sqlalchemy import select

from backend.app.adapters.base import NormalizedDailyBar
from backend.app.db.session import SessionLocal
from backend.app.models import DatasetVersion
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.repositories.datasets import DatasetRepository
from backend.app.repositories.snapshots import SnapshotRepository
from backend.app.services.dataset_version_publisher import DatasetVersionPublisher
from backend.app.services.research_data_service import ResearchDataService


def _bar(close: float) -> NormalizedDailyBar:
    return NormalizedDailyBar(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        trade_date=date(2026, 6, 1),
        open=close,
        high=close,
        low=close,
        close=close,
        pre_close=close,
        volume=1.0,
        amount=close,
        adjust_factor=1.0,
        adjust_type="none",
        source="fixture",
        ingested_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )


def _publisher(db, lake_root):
    repository = DailyBarRepository(lake_root=lake_root)
    DatasetRepository(db).upsert_daily_bars_dataset(
        source="fixture",
        row_count=repository.count(),
        latest_data_date=repository.latest_trade_date(),
        path=str(repository.dataset_dir),
    )
    return repository, DatasetVersionPublisher(db, lake_root=lake_root, source_repo=repository)


def _publish_bundle(db, lake_root):
    repository = DailyBarRepository(lake_root=lake_root)
    base = _bar(100.0)
    repository.write_many(
        [base, replace(base, adjust_type="qfq", close=90.0), replace(base, adjust_type="hfq", close=110.0)]
    )
    DatasetRepository(db).upsert_daily_bars_dataset(
        source="fixture",
        row_count=repository.count(),
        latest_data_date=repository.latest_trade_date(),
        path=str(repository.dataset_dir),
    )
    publisher = DatasetVersionPublisher(db, lake_root=lake_root, source_repo=repository)
    versions = {
        adjust_type: publisher.publish_daily_bars(adjust_type=adjust_type)
        for adjust_type in ("none", "qfq", "hfq")
    }
    return repository, versions


def test_publisher_reuses_identical_content_version(client, tmp_path):
    db = SessionLocal()
    try:
        repository = DailyBarRepository(lake_root=tmp_path / "lake")
        repository.write_many([_bar(100.0)])
        _, publisher = _publisher(db, tmp_path / "lake")

        first = publisher.publish_daily_bars(adjust_type="none")
        second = publisher.publish_daily_bars(adjust_type="none")
        db.commit()

        assert first is not None
        assert second is not None
        assert second.id == first.id
        assert db.scalars(select(DatasetVersion)).all() == [first]
        assert first.status == "published"
        assert first.partitions[0].relative_uri.startswith("versions/_objects/daily_bars/none/market=")
    finally:
        db.close()


def test_published_version_and_snapshot_are_immutable_after_silver_update(client, tmp_path):
    lake_root = tmp_path / "lake"
    db = SessionLocal()
    try:
        repository, versions = _publish_bundle(db, lake_root)
        first = versions["none"]
        assert first is not None
        assert all(version is not None for version in versions.values())

        snapshot_repo = SnapshotRepository(db)
        snapshot = snapshot_repo.create_draft(name="immutable-v1")
        for adjust_type, version in versions.items():
            snapshot_repo.add_member(snapshot, dataset=first.dataset, version=version, role=f"bars-{adjust_type}")
        snapshot_repo.activate(snapshot)
        old_partition = lake_root / first.partitions[0].relative_uri
        old_bytes = old_partition.read_bytes()

        repository.write_many([_bar(200.0)])
        second = DatasetVersionPublisher(db, lake_root=lake_root, source_repo=repository).publish_daily_bars(
            adjust_type="none"
        )
        db.commit()

        assert second is not None
        assert second.id != first.id
        assert old_partition.read_bytes() == old_bytes
        payload = ResearchDataService(db, lake_root=lake_root).read_bars(
            symbol="600519",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1),
            snapshot_id=snapshot.id,
        )
        assert payload["items"][0]["close"] == 100.0
        assert payload["contract"]["dataset_version_id"] == first.id
    finally:
        db.close()


def test_publisher_rejects_tampered_existing_content_directory(client, tmp_path):
    lake_root = tmp_path / "lake"
    db = SessionLocal()
    try:
        repository = DailyBarRepository(lake_root=lake_root)
        repository.write_many([_bar(100.0)])
        _, publisher = _publisher(db, lake_root)
        version = publisher.publish_daily_bars(adjust_type="none")
        assert version is not None
        (lake_root / version.partitions[0].relative_uri).write_bytes(b"tampered")

        try:
            publisher.publish_daily_bars(adjust_type="none")
        except RuntimeError as exc:
            assert "mismatch" in str(exc)
        else:
            raise AssertionError("tampered immutable version was accepted")
    finally:
        db.close()
