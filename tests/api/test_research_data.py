from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date

import pytest
from backend.app.adapters.base import NormalizedDailyBar
from backend.app.db.session import SessionLocal, configure_database, init_db
from backend.app.models import Dataset, DatasetVersion, DatasetVersionPartition, IngestBatch, SyncTask
from backend.app.repositories.datasets import DatasetRepository
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.repositories.snapshots import SnapshotRepository
from backend.app.services.dataset_manifest import DatasetManifestStore
from backend.app.services.research_data_service import ResearchDataService


def make_bar(symbol: str, trade_date: date, close: float) -> NormalizedDailyBar:
    return NormalizedDailyBar(
        symbol=symbol,
        exchange="SSE" if symbol.startswith("6") else "SZSE",
        market="A_SHARE",
        trade_date=trade_date,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        pre_close=None,
        volume=1000.0,
        amount=close * 1000.0,
        adjust_factor=1.0,
        adjust_type="none",
        source="fixture",
    )


def add_snapshot_bundle(db, snapshot, dataset, none_version) -> None:
    bundle_key = "fixture-bundle"
    none_version.bundle_key = bundle_key
    repository = SnapshotRepository(db)
    repository.add_member(snapshot, dataset=dataset, version=none_version, role="bars-none")
    for offset, adjust_type in enumerate(("qfq", "hfq"), start=1):
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_seq=none_version.version_seq + offset,
            version_key=f"{none_version.version_seq + offset:064d}",
            status="published",
            schema_version=none_version.schema_version,
            normalize_version=none_version.normalize_version,
            schema_sha256=none_version.schema_sha256,
            adjust_type=adjust_type,
            bundle_key=bundle_key,
            quality_status="good",
            row_count=none_version.row_count,
            min_trade_date=none_version.min_trade_date,
            max_trade_date=none_version.max_trade_date,
            manifest_uri=f"versions/daily_bars/fixture-{adjust_type}.json",
            manifest_sha256=f"{10 + offset:064d}",
        )
        db.add(version)
        db.flush()
        repository.add_member(snapshot, dataset=dataset, version=version, role=f"bars-{adjust_type}")


def test_bar_reader_returns_governed_daily_bars_with_contract_metadata(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")
    service.daily_bar_repo.write_many(
        [
            make_bar("600519", date(2026, 6, 1), 1680.0),
            make_bar("600519", date(2026, 6, 2), 1690.0),
            make_bar("000001", date(2026, 6, 1), 12.0),
        ]
    )

    payload = service.read_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
    )

    assert payload["contract"] == {
        "name": "BarReader",
        "dataset": "daily_bars",
        "layer": "silver",
        "adjust_type": "none",
        "source_policy": "governed_only",
        "manifest": {
            "dataset_name": "daily_bars",
            "layer": "silver",
            "storage_type": "parquet",
            "source": "unknown",
            "row_count": 0,
            "latest_data_date": None,
            "quality_status": "unknown",
            "updated_at": None,
            "latest_ingest_batch": None,
        },
    }
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["start_date"] == date(2026, 6, 1)
    assert payload["end_date"] == date(2026, 6, 2)
    assert payload["page"] == 1
    assert payload["page_size"] == 5000
    assert payload["total"] == 2
    assert [item["trade_date"] for item in payload["items"]] == [date(2026, 6, 1), date(2026, 6, 2)]
    assert [item["close"] for item in payload["items"]] == [1680.0, 1690.0]


def test_bar_reader_filters_declared_adjust_type_when_multiple_variants_exist(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")
    none_bar = make_bar("600519", date(2026, 6, 1), 1680.0)
    qfq_bar = NormalizedDailyBar(
        symbol="600519",
        exchange="SSE",
        market="A_SHARE",
        trade_date=date(2026, 6, 1),
        open=1600.0,
        high=1601.0,
        low=1599.0,
        close=1600.0,
        pre_close=None,
        volume=1000.0,
        amount=1600000.0,
        adjust_factor=1.0,
        adjust_type="qfq",
        source="fixture",
    )
    service.daily_bar_repo.write_many([none_bar, qfq_bar])

    payload = service.read_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
    )

    assert payload["total"] == 1
    assert [item["adjust_type"] for item in payload["items"]] == ["none"]


def test_bar_reader_rejects_blank_symbol(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")

    with pytest.raises(ValueError, match="symbol"):
        service.read_bars(
            symbol=" ",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
        )


def test_bar_reader_rejects_reversed_date_range(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")

    with pytest.raises(ValueError, match="start_date"):
        service.read_bars(
            symbol="600519",
            market="A_SHARE",
            start_date=date(2026, 6, 2),
            end_date=date(2026, 6, 1),
        )


def test_bar_reader_does_not_mix_adjustment_types(tmp_path):
    service = ResearchDataService(lake_root=tmp_path / "lake")
    base = make_bar("600519", date(2026, 6, 1), 1680.0)
    service.daily_bar_repo.write_many(
        [
            base,
            replace(base, adjust_type="qfq", close=1600.0),
            replace(base, adjust_type="hfq", close=1760.0),
        ]
    )

    payload = service.read_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
        adjust_type="qfq",
    )

    assert payload["contract"]["adjust_type"] == "qfq"
    assert payload["total"] == 1
    assert [item["adjust_type"] for item in payload["items"]] == ["qfq"]
    assert [item["close"] for item in payload["items"]] == [1600.0]


def test_bar_reader_snapshot_id_reads_the_published_version_partition(tmp_path):
    lake_root = tmp_path / "lake"
    configure_database(f"sqlite:///{tmp_path / 'snapshot.db'}")
    init_db(drop_all=True)
    version_repo = DailyBarRepository(
        lake_root=lake_root,
        dataset_dir=lake_root / "versions" / "daily_bars" / "v1",
    )
    version_repo.write_many([make_bar("600519", date(2026, 6, 1), 1888.0)])
    partition_path = next(
        (lake_root / "versions" / "daily_bars" / "v1").glob("market=*/trade_date=*/part-*.parquet")
    )
    partition_bytes = partition_path.read_bytes()
    partition_uri = "versions/daily_bars/v1/market=A_SHARE/trade_date=2026-06-01/part-000.parquet"
    manifest = {
        "manifest_version": "v1",
        "dataset": "daily_bars",
        "dataset_version_id": "daily-bars-none-v1",
        "schema_version": "v1",
        "normalize_version": "v1",
        "schema_sha256": "b" * 64,
        "adjust_type": "none",
        "bundle_key": "fixture-bundle",
        "row_count": 1,
        "min_trade_date": "2026-06-01",
        "max_trade_date": "2026-06-01",
        "partitions": [
            {
                "key": {"market": "A_SHARE", "trade_date": "2026-06-01"},
                "uri": partition_uri,
                "sha256": hashlib.sha256(partition_bytes).hexdigest(),
                "byte_size": len(partition_bytes),
                "row_count": 1,
                "min_trade_date": "2026-06-01",
                "max_trade_date": "2026-06-01",
            }
        ],
    }
    manifest_artifact = DatasetManifestStore(lake_root).write(manifest)

    db = SessionLocal()
    try:
        dataset = Dataset(
            name="daily_bars",
            layer="silver",
            storage_type="parquet",
            source="fixture",
        )
        db.add(dataset)
        db.flush()
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_seq=1,
            version_key="a" * 64,
            status="published",
            schema_version="v1",
            normalize_version="v1",
            schema_sha256="b" * 64,
            adjust_type="none",
            quality_status="good",
            row_count=1,
            min_trade_date=date(2026, 6, 1),
            max_trade_date=date(2026, 6, 1),
            manifest_uri=manifest_artifact.relative_uri,
            manifest_sha256=manifest_artifact.sha256,
            partitions=[
                DatasetVersionPartition(
                    partition_spec_json={"market": "A_SHARE", "trade_date": "2026-06-01"},
                    relative_uri=partition_uri,
                    sha256=hashlib.sha256(partition_bytes).hexdigest(),
                    byte_size=len(partition_bytes),
                    row_count=1,
                    min_trade_date=date(2026, 6, 1),
                    max_trade_date=date(2026, 6, 1),
                    status="sealed",
                )
            ],
        )
        db.add(version)
        db.flush()
        snapshot = SnapshotRepository(db).create_draft(name="research-v1")
        add_snapshot_bundle(db, snapshot, dataset, version)
        SnapshotRepository(db).activate(snapshot)
        db.commit()

        payload = ResearchDataService(db, lake_root=lake_root).read_bars(
            symbol="600519",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1),
            snapshot_id=snapshot.id,
        )
    finally:
        db.close()

    assert payload["items"][0]["close"] == 1888.0
    assert payload["contract"]["snapshot_id"] == snapshot.id
    assert payload["contract"]["dataset_version_id"] == version.id
    assert payload["contract"]["manifest_sha256"] == manifest_artifact.sha256


def test_bar_reader_rejects_tampered_snapshot_manifest(tmp_path):
    lake_root = tmp_path / "lake"
    configure_database(f"sqlite:///{tmp_path / 'snapshot-tampered.db'}")
    init_db(drop_all=True)
    repository = DailyBarRepository(
        lake_root=lake_root,
        dataset_dir=lake_root / "versions" / "daily_bars" / "v1",
    )
    repository.write_many([make_bar("600519", date(2026, 6, 1), 1888.0)])
    partition_path = next((lake_root / "versions" / "daily_bars" / "v1").glob("market=*/trade_date=*/part-*.parquet"))
    partition_uri = "versions/daily_bars/v1/market=A_SHARE/trade_date=2026-06-01/part-000.parquet"
    manifest = {
        "manifest_version": "v1",
        "dataset": "daily_bars",
        "dataset_version_id": "tampered-test",
        "schema_version": "v1",
        "normalize_version": "v1",
        "schema_sha256": "b" * 64,
        "adjust_type": "none",
        "bundle_key": "fixture-bundle",
        "row_count": 1,
        "partitions": [
            {
                "key": {"market": "A_SHARE", "trade_date": "2026-06-01"},
                "uri": partition_uri,
                "sha256": hashlib.sha256(partition_path.read_bytes()).hexdigest(),
                "byte_size": partition_path.stat().st_size,
                "row_count": 1,
            }
        ],
    }
    artifact = DatasetManifestStore(lake_root).write(manifest)
    manifest_path = lake_root / artifact.relative_uri
    manifest_path.write_text('{"manifest_version":"tampered"}', encoding="utf-8")

    db = SessionLocal()
    try:
        dataset = Dataset(name="daily_bars", layer="silver", storage_type="parquet", source="fixture")
        db.add(dataset)
        db.flush()
        version = DatasetVersion(
            dataset_id=dataset.id,
            version_seq=1,
            version_key=artifact.sha256,
            status="published",
            schema_version="v1",
            normalize_version="v1",
            schema_sha256="b" * 64,
            adjust_type="none",
            quality_status="good",
            row_count=1,
            manifest_uri=artifact.relative_uri,
            manifest_sha256=artifact.sha256,
            partitions=[
                DatasetVersionPartition(
                    partition_spec_json={"market": "A_SHARE", "trade_date": "2026-06-01"},
                    relative_uri=partition_uri,
                    sha256=hashlib.sha256(partition_path.read_bytes()).hexdigest(),
                    byte_size=partition_path.stat().st_size,
                    row_count=1,
                    status="sealed",
                )
            ],
        )
        db.add(version)
        db.flush()
        snapshot = SnapshotRepository(db).create_draft(name="tampered-manifest")
        add_snapshot_bundle(db, snapshot, dataset, version)
        SnapshotRepository(db).activate(snapshot)
        db.commit()
        with pytest.raises(ValueError, match="manifest"):
            ResearchDataService(db, lake_root=lake_root).read_bars(
                symbol="600519",
                market="A_SHARE",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 1),
                snapshot_id=snapshot.id,
            )
    finally:
        db.close()


def test_research_bars_api_reads_governed_daily_bars(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    service = ResearchDataService()
    service.daily_bar_repo.write_many(
        [
            make_bar("600519", date(2026, 6, 1), 1680.0),
            make_bar("600519", date(2026, 6, 2), 1690.0),
            make_bar("000001", date(2026, 6, 1), 12.0),
        ]
    )
    with SessionLocal() as db:
        DatasetRepository(db).upsert_daily_bars_dataset(
            source="fixture",
            row_count=3,
            latest_data_date=date(2026, 6, 2),
            path=str(tmp_path / "lake" / "silver" / "daily_bars"),
        )
        task = SyncTask(
            task_type="daily_bars",
            source="fixture",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            status="success",
        )
        db.add(task)
        db.flush()
        db.add(
            IngestBatch(
                task_id=task.id,
                dataset_name="daily_bars",
                source="fixture",
                requested_source="auto",
                market="A_SHARE",
                symbol="600519",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 2),
                status="success",
                schema_version="v1",
                normalize_version="v1",
                raw_records=3,
                normalized_records=3,
                records_written=3,
                quality_status="good",
            )
        )
        db.commit()

    response = client.get(
        "/api/research-data/bars",
        params={
            "symbol": "600519",
            "market": "A_SHARE",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "page_size": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract"]["name"] == "BarReader"
    assert payload["contract"]["source_policy"] == "governed_only"
    assert payload["contract"]["manifest"]["dataset_name"] == "daily_bars"
    assert payload["contract"]["manifest"]["storage_type"] == "parquet"
    assert payload["contract"]["manifest"]["source"] == "fixture"
    assert payload["contract"]["manifest"]["row_count"] == 3
    assert payload["contract"]["manifest"]["latest_data_date"] == "2026-06-02"
    assert payload["contract"]["manifest"]["quality_status"] == "good"
    assert payload["contract"]["manifest"]["updated_at"] is not None
    assert payload["contract"]["manifest"]["latest_ingest_batch"] == {
        "id": 1,
        "task_id": 1,
        "source": "fixture",
        "requested_source": "auto",
        "market": "A_SHARE",
        "symbol": "600519",
        "start_date": "2026-06-01",
        "end_date": "2026-06-02",
        "status": "success",
        "schema_version": "v1",
        "normalize_version": "v1",
        "records_written": 3,
        "quality_status": "good",
    }
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert [item["trade_date"] for item in payload["items"]] == ["2026-06-01"]


def test_research_bars_api_rejects_reversed_date_range(client):
    response = client.get(
        "/api/research-data/bars",
        params={
            "symbol": "600519",
            "market": "A_SHARE",
            "start_date": "2026-06-02",
            "end_date": "2026-06-01",
        },
    )

    assert response.status_code == 400
