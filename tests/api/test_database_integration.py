from __future__ import annotations

from datetime import date, datetime, timezone

from backend.app.adapters.base import NormalizedDailyBar
from backend.app.core.config import get_settings
from backend.app.db.session import SessionLocal
from backend.app.models import Dataset, IngestBatch, Stock, SyncTask, TradingCalendar
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.services.database_integration_service import DatabaseIntegrationService, invalidate_coverage_cache


def test_database_integration_overview_returns_empty_state(client):
    response = client.get("/api/database/integration-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["datasets_total"] == 0
    assert payload["summary"]["total_rows"] == 0
    assert payload["summary"]["recent_batches_total"] == 0
    assert payload["coverage_summary"] == {
        "market": "A_SHARE",
        "coverage_status": "ok",
        "coverage_message": None,
        "stock_pool_total": 0,
        "daily_covered_stock_count": 0,
        "calendar_latest_date": None,
        "coverage_start_date": None,
        "coverage_end_date": None,
        "daily_expected_symbol_days": 0,
        "daily_actual_symbol_days": 0,
        "daily_missing_symbol_days": 0,
        "daily_completeness": None,
    }
    assert payload["dataset_snapshots"] == []
    assert payload["sync_watermarks"] == []
    assert payload["provider_integrations"] == []
    assert payload["recent_batches"] == []


def test_database_integration_overview_summarizes_datasets_batches_and_providers(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    industry="白酒",
                    listing_date=date(2001, 8, 27),
                    source="fixture",
                ),
                Stock(
                    symbol="000001",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="平安银行",
                    status="LISTED",
                    industry="银行",
                    listing_date=date(1991, 4, 3),
                    source="fixture",
                ),
                Dataset(
                    name="stocks",
                    layer="silver",
                    storage_type="postgres",
                    schema_json={"symbol": "string", "name": "string"},
                    primary_keys_json=["symbol", "exchange", "market"],
                    partition_keys_json=["market"],
                    source="akshare",
                    row_count=5300,
                    latest_data_date=date(2026, 6, 5),
                    quality_status="good",
                ),
                Dataset(
                    name="daily_bars",
                    layer="silver",
                    storage_type="parquet",
                    schema_json={"symbol": "string", "trade_date": "date", "close": "float"},
                    primary_keys_json=["market", "symbol", "trade_date", "adjust_type"],
                    partition_keys_json=["market", "trade_date"],
                    source="baostock",
                    row_count=24000,
                    latest_data_date=date(2026, 6, 4),
                    quality_status="warning",
                ),
            ]
        )
        task = SyncTask(
            task_type="daily_bars",
            source="auto",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status="success",
            records_read=5,
            records_written=5,
            finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
        )
        db.add(task)
        db.flush()
        db.add_all(
            [
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="baostock",
                    requested_source="auto",
                    market="A_SHARE",
                    symbol="600519",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 5),
                    status="success",
                    schema_version="v1",
                    normalize_version="v1",
                    raw_records=5,
                    normalized_records=5,
                    records_written=5,
                    validation_errors_json=[],
                    quality_status="good",
                    started_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
                ),
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="akshare",
                    requested_source="akshare",
                    market="A_SHARE",
                    symbol="600519",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 5),
                    status="failed",
                    schema_version="v1",
                    normalize_version="v1",
                    raw_records=0,
                    normalized_records=0,
                    records_written=0,
                    validation_errors_json=["upstream timeout"],
                    quality_status="failed",
                    error_message="upstream timeout",
                    started_at=datetime(2026, 6, 6, 8, 59, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 6, 6, 8, 59, tzinfo=timezone.utc),
                ),
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=False, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 3), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    DailyBarRepository(lake_root=lake_root).write_many(
        [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                pre_close=None,
                volume=1000.0,
                amount=100500.0,
                adjust_factor=1.0,
                adjust_type="none",
                source="fixture",
            ),
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                pre_close=None,
                volume=1000.0,
                amount=100500.0,
                adjust_factor=1.0,
                adjust_type="qfq",
                source="fixture",
            ),
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 3),
                open=101.0,
                high=102.0,
                low=100.0,
                close=101.5,
                pre_close=100.5,
                volume=1200.0,
                amount=121800.0,
                adjust_factor=1.0,
                source="fixture",
            ),
        ]
    )

    response = client.get("/api/database/integration-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["datasets_total"] == 2
    assert payload["summary"]["total_rows"] == 29300
    assert payload["summary"]["latest_data_date"] == "2026-06-05"
    assert payload["summary"]["recent_batches_total"] == 2
    assert payload["summary"]["failed_batches_total"] == 1
    assert payload["summary"]["fallback_successes_total"] == 1
    assert payload["summary"]["healthy_providers_total"] == 1
    assert payload["coverage_summary"] == {
        "market": "A_SHARE",
        "coverage_status": "ok",
        "coverage_message": None,
        "stock_pool_total": 2,
        "daily_covered_stock_count": 1,
        "calendar_latest_date": "2026-06-03",
        "coverage_start_date": "2025-12-05",
        "coverage_end_date": "2026-06-03",
        "daily_expected_symbol_days": 4,
        "daily_actual_symbol_days": 2,
        "daily_missing_symbol_days": 2,
        "daily_completeness": 0.5,
    }

    snapshots = {item["dataset_name"]: item for item in payload["dataset_snapshots"]}
    assert snapshots["stocks"]["schema_fields_count"] == 2
    assert snapshots["stocks"]["dataset_version"].startswith("silver-")
    assert snapshots["daily_bars"]["quality_status"] == "warning"

    watermark = payload["sync_watermarks"][0]
    assert watermark["dataset_name"] == "daily_bars"
    assert watermark["source"] == "baostock"
    assert watermark["requested_source"] == "auto"
    assert watermark["symbol"] == "600519"
    assert watermark["latest_success_date"] == "2026-06-05"
    assert watermark["records_written"] == 5
    assert watermark["repair_start_date"] is None
    assert watermark["repair_end_date"] is None
    assert "1/2" in watermark["repair_reason"]

    failed_watermark = next(item for item in payload["sync_watermarks"] if item["source"] == "akshare")
    assert failed_watermark["requested_source"] == "akshare"


def test_database_integration_overview_refreshes_after_coverage_cache_invalidation(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    industry="白酒",
                    listing_date=date(2001, 8, 27),
                    source="fixture",
                ),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    service = DatabaseIntegrationService(SessionLocal())
    first = service.get_overview(market="A_SHARE", use_cache=True)

    db = SessionLocal()
    try:
        db.add(TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"))
        db.commit()
    finally:
        db.close()

    second_cached = service.get_overview(market="A_SHARE", use_cache=True)
    assert second_cached["coverage_summary"]["daily_expected_symbol_days"] == first["coverage_summary"]["daily_expected_symbol_days"]
    assert second_cached["coverage_summary"]["calendar_latest_date"] == date(2026, 6, 1)

    invalidate_coverage_cache("A_SHARE")
    refreshed = DatabaseIntegrationService(SessionLocal()).get_overview(market="A_SHARE", use_cache=True)
    assert refreshed["coverage_summary"]["daily_expected_symbol_days"] == first["coverage_summary"]["daily_expected_symbol_days"] + 1
    assert refreshed["coverage_summary"]["calendar_latest_date"] == date(2026, 6, 2)
    assert refreshed["coverage_summary"]["coverage_start_date"] == date(2025, 12, 4)


def test_database_integration_overview_counts_only_listed_common_a_share_stock_pool(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(symbol="600519", exchange="SSE", market="A_SHARE", name="贵州茅台", status="LISTED", source="fixture"),
                Stock(symbol="000001", exchange="SZSE", market="A_SHARE", name="平安银行", status="LISTED", source="fixture"),
                Stock(symbol="430047", exchange="BSE", market="A_SHARE", name="北交所样本", status="LISTED", source="fixture"),
                Stock(symbol="000016", exchange="SSE", market="A_SHARE", name="上证50指数", status="LISTED", source="fixture"),
                Stock(symbol="159001", exchange="SZSE", market="A_SHARE", name="货币ETF", status="LISTED", source="fixture"),
                Stock(symbol="600001", exchange="SSE", market="A_SHARE", name="退市样本", status="DELISTED", source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    DailyBarRepository(lake_root=lake_root).write_many(
        [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                pre_close=None,
                volume=1000.0,
                amount=100500.0,
                adjust_factor=1.0,
                source="fixture",
            ),
            NormalizedDailyBar(
                symbol="000016",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=3000.0,
                high=3010.0,
                low=2990.0,
                close=3005.0,
                pre_close=None,
                volume=1000.0,
                amount=3005000.0,
                adjust_factor=1.0,
                source="fixture",
            ),
        ]
    )

    response = client.get("/api/database/integration-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage_summary"]["stock_pool_total"] == 3
    assert payload["coverage_summary"]["daily_covered_stock_count"] == 1
    assert payload["coverage_summary"]["daily_expected_symbol_days"] == 3
    assert payload["coverage_summary"]["daily_actual_symbol_days"] == 1
    assert payload["coverage_summary"]["daily_missing_symbol_days"] == 2


def test_database_integration_overview_uses_half_year_daily_bar_target_window(client):
    db = SessionLocal()
    try:
        db.add(Stock(symbol="600519", exchange="SSE", market="A_SHARE", name="贵州茅台", status="LISTED", source="fixture"))
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2025, 12, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 5), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/database/integration-overview")

    assert response.status_code == 200
    coverage = response.json()["coverage_summary"]
    assert coverage["calendar_latest_date"] == "2026-06-05"
    assert coverage["coverage_start_date"] == "2025-12-07"
    assert coverage["coverage_end_date"] == "2026-06-05"
    assert coverage["daily_expected_symbol_days"] == 1
    assert coverage["daily_actual_symbol_days"] == 0
    assert coverage["daily_missing_symbol_days"] == 1


def test_database_integration_overview_projects_stale_stock_dataset_count_to_common_pool(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(symbol="600519", exchange="SSE", market="A_SHARE", name="贵州茅台", status="LISTED", source="fixture"),
                Stock(symbol="000001", exchange="SZSE", market="A_SHARE", name="平安银行", status="LISTED", source="fixture"),
                Stock(symbol="430047", exchange="BSE", market="A_SHARE", name="北交所样本", status="LISTED", source="fixture"),
                Stock(symbol="000016", exchange="SSE", market="A_SHARE", name="上证50指数", status="LISTED", source="fixture"),
                Stock(symbol="159001", exchange="SZSE", market="A_SHARE", name="货币ETF", status="LISTED", source="fixture"),
                Dataset(
                    name="stocks",
                    layer="silver",
                    storage_type="postgres",
                    schema_json={"symbol": "string"},
                    primary_keys_json=["symbol", "exchange", "market"],
                    partition_keys_json=["market"],
                    source="baostock",
                    row_count=5,
                    latest_data_date=date(2026, 6, 17),
                    quality_status="good",
                ),
                Dataset(
                    name="daily_bars",
                    layer="silver",
                    storage_type="parquet",
                    schema_json={"symbol": "string", "trade_date": "date"},
                    primary_keys_json=["symbol", "exchange", "market", "trade_date"],
                    partition_keys_json=["market", "trade_date"],
                    source="baostock",
                    row_count=2,
                    latest_data_date=date(2026, 6, 5),
                    quality_status="good",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/database/integration-overview")

    assert response.status_code == 200
    payload = response.json()
    snapshots = {item["dataset_name"]: item for item in payload["dataset_snapshots"]}
    assert payload["coverage_summary"]["stock_pool_total"] == 3
    assert snapshots["stocks"]["row_count"] == 3
    assert payload["summary"]["total_rows"] == 5


def test_database_integration_overview_ignores_zero_write_success_for_watermarks(client):
    db = SessionLocal()
    try:
        task = SyncTask(
            task_type="daily_bars_market_repair",
            source="baostock",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
            status="success",
            records_read=4,
            records_written=4,
            finished_at=datetime(2026, 6, 6, 9, 2, tzinfo=timezone.utc),
        )
        db.add(task)
        db.flush()
        db.add_all(
            [
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="baostock",
                    requested_source="baostock",
                    market="A_SHARE",
                    symbol="600519",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 5),
                    status="success",
                    schema_version="v1",
                    normalize_version="v1",
                    raw_records=4,
                    normalized_records=4,
                    records_written=4,
                    validation_errors_json=[],
                    quality_status="good",
                    started_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
                ),
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="baostock",
                    requested_source="baostock",
                    market="A_SHARE",
                    symbol="600519",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 6),
                    status="success",
                    schema_version="v1",
                    normalize_version="v1",
                    raw_records=0,
                    normalized_records=0,
                    records_written=0,
                    validation_errors_json=[],
                    quality_status="good",
                    started_at=datetime(2026, 6, 6, 9, 2, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 6, 6, 9, 2, tzinfo=timezone.utc),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/database/integration-overview")

    assert response.status_code == 200
    payload = response.json()
    watermarks = [item for item in payload["sync_watermarks"] if item["dataset_name"] == "daily_bars"]
    assert len(watermarks) == 1
    assert watermarks[0]["records_written"] == 4
    assert watermarks[0]["latest_success_date"] == "2026-06-05"
    assert watermarks[0]["last_success_at"] == "2026-06-06T09:01:00"

    providers = {item["source"]: item for item in payload["provider_integrations"]}
    assert providers["baostock"]["attempts"] == 2
    assert providers["baostock"]["successes"] == 1
    assert providers["baostock"]["records_written"] == 4
    assert providers["baostock"]["last_success_at"] == "2026-06-06T09:01:00"


def test_database_integration_overview_filters_market_scope(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    source="fixture",
                ),
                Stock(
                    symbol="00700",
                    exchange="HKEX",
                    market="HK",
                    name="腾讯控股",
                    status="LISTED",
                    source="fixture",
                ),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="HK", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
            ]
        )
        task = SyncTask(
            task_type="daily_bars",
            source="auto",
            market="HK",
            symbol="00700",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1),
            status="success",
            records_read=1,
            records_written=1,
            finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
        )
        db.add(task)
        db.flush()
        db.add(
            IngestBatch(
                task_id=task.id,
                dataset_name="daily_bars",
                source="akshare",
                requested_source="auto",
                market="HK",
                symbol="00700",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 1),
                status="success",
                schema_version="v1",
                normalize_version="v1",
                raw_records=1,
                normalized_records=1,
                records_written=1,
                validation_errors_json=[],
                quality_status="good",
                started_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()

    DailyBarRepository(lake_root=lake_root).write_many(
        [
            NormalizedDailyBar(
                symbol="00700",
                exchange="HKEX",
                market="HK",
                trade_date=date(2026, 6, 1),
                open=400.0,
                high=405.0,
                low=398.0,
                close=402.0,
                pre_close=None,
                volume=1000.0,
                amount=402000.0,
                adjust_factor=1.0,
                source="fixture",
            )
        ]
    )

    response = client.get("/api/database/integration-overview?market=hk")

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage_summary"] == {
        "market": "HK",
        "coverage_status": "ok",
        "coverage_message": None,
        "stock_pool_total": 1,
        "daily_covered_stock_count": 1,
        "calendar_latest_date": "2026-06-01",
        "coverage_start_date": "2025-12-03",
        "coverage_end_date": "2026-06-01",
        "daily_expected_symbol_days": 1,
        "daily_actual_symbol_days": 1,
        "daily_missing_symbol_days": 0,
        "daily_completeness": 1.0,
    }
    assert payload["summary"]["recent_batches_total"] == 1
    assert payload["recent_batches"][0]["market"] == "HK"
    assert payload["sync_watermarks"][0]["market"] == "HK"
    assert payload["provider_integrations"][0]["source"] == "akshare"


def test_database_integration_overview_degrades_when_coverage_query_fails(client, monkeypatch):
    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    source="fixture",
                ),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    def raise_coverage_error(self, *, market: str):  # noqa: ANN001
        raise RuntimeError(f"{market} parquet scan failed")

    monkeypatch.setattr(DailyBarRepository, "market_symbol_trade_date_pairs", raise_coverage_error)

    response = client.get("/api/database/integration-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage_summary"]["market"] == "A_SHARE"
    assert payload["coverage_summary"]["coverage_status"] == "degraded"
    assert "Parquet" in payload["coverage_summary"]["coverage_message"]
    assert "DuckDB" in payload["coverage_summary"]["coverage_message"]
    assert payload["coverage_summary"]["stock_pool_total"] == 1
    assert payload["coverage_summary"]["calendar_latest_date"] == "2026-06-01"
    assert payload["coverage_summary"]["daily_expected_symbol_days"] == 1
    assert payload["coverage_summary"]["daily_actual_symbol_days"] == 0
    assert payload["coverage_summary"]["daily_missing_symbol_days"] == 0
    assert payload["coverage_summary"]["daily_completeness"] is None


def test_database_lineage_filters_batches_by_dataset_symbol_and_date(client):
    db = SessionLocal()
    try:
        task = SyncTask(
            task_type="daily_bars",
            source="auto",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status="success",
            records_read=5,
            records_written=5,
            finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
        )
        db.add(task)
        db.flush()
        db.add_all(
            [
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="baostock",
                    requested_source="auto",
                    market="A_SHARE",
                    symbol="600519",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 5),
                    status="success",
                    schema_version="bars-v1",
                    normalize_version="normalize-v1",
                    raw_records=5,
                    normalized_records=5,
                    records_written=5,
                    validation_errors_json=[],
                    quality_status="good",
                    started_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
                ),
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="baostock",
                    requested_source="auto",
                    market="A_SHARE",
                    symbol="600000",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 5),
                    status="success",
                    schema_version="bars-v1",
                    normalize_version="normalize-v1",
                    raw_records=5,
                    normalized_records=5,
                    records_written=5,
                    validation_errors_json=[],
                    quality_status="good",
                    started_at=datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 6, 6, 8, 1, tzinfo=timezone.utc),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/database/lineage",
        params={
            "dataset_name": "daily_bars",
            "market": "a_share",
            "symbol": "600519",
            "trade_date": "2026-06-03",
            "page": 1,
            "page_size": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 10
    assert payload["total_pages"] == 1

    item = payload["items"][0]
    assert item["dataset_name"] == "daily_bars"
    assert item["symbol"] == "600519"
    assert item["market"] == "A_SHARE"
    assert item["source"] == "baostock"
    assert item["requested_source"] == "auto"
    assert item["task_id"] == task.id
    assert item["task_type"] == "daily_bars"
    assert item["task_status"] == "success"
    assert item["task_source"] == "auto"
    assert item["schema_version"] == "bars-v1"
    assert item["normalize_version"] == "normalize-v1"
    assert item["raw_records"] == 5
    assert item["normalized_records"] == 5
    assert item["records_written"] == 5
    assert item["quality_status"] == "good"


def test_database_lineage_filters_by_exact_batch_id(client):
    db = SessionLocal()
    try:
        task = SyncTask(
            task_type="daily_bars",
            source="auto",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status="success",
            records_read=5,
            records_written=5,
            finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
        )
        db.add(task)
        db.flush()
        target_batch = IngestBatch(
            task_id=task.id,
            dataset_name="daily_bars",
            source="baostock",
            requested_source="auto",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status="success",
            schema_version="bars-v1",
            normalize_version="normalize-v1",
            raw_records=5,
            normalized_records=5,
            records_written=5,
            validation_errors_json=[],
            quality_status="good",
            started_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
        )
        other_batch = IngestBatch(
            task_id=task.id,
            dataset_name="daily_bars",
            source="baostock",
            requested_source="auto",
            market="A_SHARE",
            symbol="600000",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status="success",
            schema_version="bars-v1",
            normalize_version="normalize-v1",
            raw_records=5,
            normalized_records=5,
            records_written=5,
            validation_errors_json=[],
            quality_status="good",
            started_at=datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 6, 8, 1, tzinfo=timezone.utc),
        )
        db.add_all([target_batch, other_batch])
        db.commit()
        target_batch_id = target_batch.id
    finally:
        db.close()

    response = client.get(
        "/api/database/lineage",
        params={
            "batch_id": target_batch_id,
            "dataset_name": "daily_bars",
            "market": "A_SHARE",
            "trade_date": "2026-06-03",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == target_batch_id
    assert payload["items"][0]["symbol"] == "600519"


def test_database_lineage_returns_empty_when_date_outside_batch_range(client):
    db = SessionLocal()
    try:
        task = SyncTask(
            task_type="daily_bars",
            source="baostock",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 5),
            status="failed",
            error_message="upstream timeout",
            finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
        )
        db.add(task)
        db.flush()
        db.add(
            IngestBatch(
                task_id=task.id,
                dataset_name="daily_bars",
                source="baostock",
                requested_source="baostock",
                market="A_SHARE",
                symbol="600519",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 5),
                status="failed",
                schema_version="bars-v1",
                normalize_version="normalize-v1",
                raw_records=0,
                normalized_records=0,
                records_written=0,
                validation_errors_json=["upstream timeout"],
                error_message="upstream timeout",
                quality_status="failed",
                started_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/database/lineage",
        params={
            "dataset_name": "daily_bars",
            "market": "A_SHARE",
            "symbol": "600519",
            "trade_date": "2026-06-09",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0
