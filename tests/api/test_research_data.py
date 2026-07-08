from __future__ import annotations

from datetime import date

import pytest

from backend.app.adapters.base import NormalizedDailyBar
from backend.app.db.session import SessionLocal
from backend.app.models import IngestBatch, SyncTask
from backend.app.repositories.datasets import DatasetRepository
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
