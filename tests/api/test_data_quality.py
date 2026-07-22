from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models import DataQualityReport, Dataset, IngestBatch, Stock, SyncTask, TradingCalendar
from backend.app.repositories.daily_bars import DAILY_BAR_ARROW_SCHEMA, DailyBarRepository
from backend.app.services.data_quality_service import DataQualityService


def seed_quality_datasets() -> None:
    db = SessionLocal()
    try:
        db.add_all(
            [
                Dataset(
                    name="stocks",
                    layer="silver",
                    storage_type="postgres",
                    schema_json={"symbol": "string"},
                    primary_keys_json=["symbol", "exchange", "market"],
                    partition_keys_json=["market"],
                    source="akshare",
                    row_count=10,
                    latest_data_date=date(2026, 6, 5),
                    quality_status="unknown",
                ),
                Dataset(
                    name="daily_bars",
                    layer="silver",
                    storage_type="parquet",
                    schema_json={"symbol": "string", "trade_date": "date"},
                    primary_keys_json=["symbol", "exchange", "market", "trade_date"],
                    partition_keys_json=["market", "trade_date"],
                    source="baostock",
                    row_count=0,
                    latest_data_date=None,
                    quality_status="unknown",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_data_quality_overview_before_reports(client):
    seed_quality_datasets()

    response = client.get("/api/data-quality/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["datasets_total"] == 2
    assert payload["datasets_unknown"] == 2
    assert payload["reports_total"] == 0
    assert payload["latest_checked_at"] is None


def test_data_quality_overview_projects_row_count_and_quality_status_before_aggregating(client):
    seed_quality_datasets()
    db = SessionLocal()
    try:
        dataset = db.scalar(select(Dataset).where(Dataset.name == "stocks"))
        daily_dataset = db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        assert dataset is not None
        assert daily_dataset is not None
        dataset.row_count = 5
        dataset.quality_status = "unknown"
        daily_dataset.quality_status = "warning"
        db.add_all(
            [
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    industry="酒",
                    source="fixture",
                ),
                Stock(
                    symbol="000001",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="平安银行",
                    status="LISTED",
                    industry="银行",
                    source="fixture",
                ),
                Stock(
                    symbol="430047",
                    exchange="BSE",
                    market="A_SHARE",
                    name="北交所样本",
                    status="LISTED",
                    industry="样本",
                    source="fixture",
                ),
                Stock(
                    symbol="700001",
                    exchange="SSE",
                    market="A_SHARE",
                    name="非共通样本1",
                    status="LISTED",
                    industry="样本",
                    source="fixture",
                ),
                Stock(
                    symbol="800001",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="非共通样本2",
                    status="LISTED",
                    industry="样本",
                    source="fixture",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/data-quality/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["datasets_good"] == 1
    assert payload["datasets_warning"] == 1
    assert payload["datasets_unknown"] == 0

    db = SessionLocal()
    try:
        dataset = db.scalar(select(Dataset).where(Dataset.name == "stocks"))
        assert dataset is not None
        assert dataset.row_count == 3
        assert dataset.quality_status == "good"
    finally:
        db.close()


def test_data_quality_check_generates_reports_and_updates_dataset_status(client):
    seed_quality_datasets()

    response = client.post("/api/data-quality/check")

    assert response.status_code == 200
    payload = response.json()
    assert payload["checked_datasets"] == 2
    assert payload["reports_created"] == 3
    assert payload["overview"]["datasets_good"] == 1
    assert payload["overview"]["datasets_warning"] == 1

    db = SessionLocal()
    try:
        statuses = {dataset.name: dataset.quality_status for dataset in db.query(Dataset).all()}
    finally:
        db.close()

    assert statuses == {"stocks": "good", "daily_bars": "warning"}


def test_data_quality_reports_support_pagination_and_filters(client):
    seed_quality_datasets()
    client.post("/api/data-quality/check")

    warning_response = client.get(
        "/api/data-quality/reports",
        params={"severity": "warning", "dataset_name": "daily", "page": 1, "page_size": 1},
    )
    good_response = client.get("/api/data-quality/reports", params={"status": "good"})

    assert warning_response.status_code == 200
    warning_payload = warning_response.json()
    assert warning_payload["total"] == 2
    assert warning_payload["page_size"] == 1
    assert warning_payload["total_pages"] == 2
    assert warning_payload["items"][0]["dataset_name"] == "daily_bars"
    assert warning_payload["items"][0]["severity"] == "warning"

    assert good_response.status_code == 200
    good_payload = good_response.json()
    assert good_payload["total"] == 1
    assert good_payload["items"][0]["dataset_name"] == "stocks"


def test_data_quality_reports_keep_history_and_default_to_latest_run(client):
    seed_quality_datasets()
    db = SessionLocal()
    try:
        service = DataQualityService(db)
        first_result = service.run_check()
        first_checked_at = first_result["checked_at"]

        daily_dataset = db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        assert daily_dataset is not None
        daily_dataset.row_count = 12
        daily_dataset.latest_data_date = date(2026, 6, 6)
        db.commit()

        second_result = service.run_check()
        second_checked_at = second_result["checked_at"]
        reports_total = db.query(DataQualityReport).count()
    finally:
        db.close()

    assert first_checked_at != second_checked_at
    assert reports_total == first_result["reports_created"] + second_result["reports_created"]

    latest_response = client.get("/api/data-quality/reports", params={"page": 1, "page_size": 20})
    history_response = client.get(
        "/api/data-quality/reports",
        params={"checked_at": first_checked_at, "page": 1, "page_size": 20},
    )
    runs_response = client.get("/api/data-quality/check-runs")

    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    assert latest_payload["checked_at"] == second_checked_at.isoformat()
    assert {item["checked_at"] for item in latest_payload["items"]} == {second_checked_at.isoformat()}

    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert history_payload["checked_at"] == first_checked_at.isoformat()
    assert {item["checked_at"] for item in history_payload["items"]} == {first_checked_at.isoformat()}

    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert [item["checked_at"] for item in runs_payload["items"]] == [
        second_checked_at.isoformat(),
        first_checked_at.isoformat(),
    ]
    assert runs_payload["items"][0]["reports_total"] == second_result["reports_created"]
    assert runs_payload["items"][1]["reports_total"] == first_result["reports_created"]


def test_data_quality_reports_include_dataset_and_latest_batch_trace(client):
    seed_quality_datasets()

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
            records_read=7,
            records_written=7,
            finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
        )
        db.add(task)
        db.flush()
        db.add(
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
                raw_records=7,
                normalized_records=7,
                records_written=7,
                validation_errors_json=[],
                quality_status="good",
                started_at=datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 6, 6, 9, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()

    client.post("/api/data-quality/check")
    response = client.get(
        "/api/data-quality/reports",
        params={"severity": "warning", "dataset_name": "daily", "page": 1, "page_size": 1},
    )

    assert response.status_code == 200
    report = response.json()["items"][0]
    trace = report["trace"]
    assert trace["dataset_source"] == "baostock"
    assert trace["storage_type"] == "parquet"
    assert trace["row_count"] == 0
    assert trace["schema_fields_count"] == 2
    assert trace["primary_keys_json"] == ["symbol", "exchange", "market", "trade_date"]
    assert trace["latest_batch_id"] is not None
    assert trace["latest_task_id"] == task.id
    assert trace["latest_batch_source"] == "baostock"
    assert trace["latest_batch_requested_source"] == "auto"
    assert trace["latest_batch_schema_version"] == "v1"
    assert trace["latest_batch_normalize_version"] == "v1"
    assert trace["latest_batch_records_written"] == 7


def test_daily_bars_quality_check_detects_market_data_issues(client, tmp_path):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    valid_row = {
        "symbol": "600519",
        "exchange": "SSE",
        "market": "A_SHARE",
        "trade_date": date(2026, 6, 1),
        "open": 10.0,
        "high": 10.8,
        "low": 9.8,
        "close": 10.5,
        "pre_close": 10.0,
        "volume": 1000.0,
        "amount": 10500.0,
        "adjust_factor": 1.0,
        "source": "akshare",
    }
    bad_row = {
        "symbol": "600519",
        "exchange": "SSE",
        "market": "A_SHARE",
        "trade_date": date(2026, 6, 3),
        "open": -10.0,
        "high": 9.0,
        "low": 11.0,
        "close": 10.5,
        "pre_close": 10.5,
        "volume": -1.0,
        "amount": -100.0,
        "adjust_factor": 1.0,
        "source": None,
    }
    write_daily_bar_partition(repo, date(2026, 6, 1), [valid_row])
    write_daily_bar_partition(repo, date(2026, 6, 3), [bad_row, bad_row])

    db = SessionLocal()
    try:
        db.add(
            Dataset(
                name="daily_bars",
                layer="silver",
                storage_type="parquet",
                path=str(repo.dataset_dir),
                schema_json={"symbol": "string", "trade_date": "date"},
                primary_keys_json=["symbol", "exchange", "market", "trade_date"],
                partition_keys_json=["market", "trade_date"],
                source="akshare",
                row_count=3,
                latest_data_date=date(2026, 6, 3),
                quality_status="unknown",
            )
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="akshare"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="akshare"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 3), is_open=True, source="akshare"),
            ]
        )
        db.commit()

        result = DataQualityService(db, lake_root=tmp_path / "lake").run_check()
        reports = list(db.scalars(select(DataQualityReport)).all())
        status = db.scalar(select(Dataset.quality_status).where(Dataset.name == "daily_bars"))
    finally:
        db.close()

    check_types = {report.check_type for report in reports}
    assert result["checked_datasets"] == 1
    assert result["overview"]["datasets_error"] == 1
    assert status == "error"
    assert {
        "duplicate_record",
        "field_completeness",
        "missing_trade_date",
        "missing_trade_date_by_symbol",
        "negative_price",
        "negative_turnover",
        "ohlc_high_bound",
        "ohlc_low_bound",
        "ohlc_range",
    }.issubset(check_types)


def test_daily_bars_quality_check_detects_symbol_level_missing_trade_dates(client, tmp_path):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    row_600519 = {
        "symbol": "600519",
        "exchange": "SSE",
        "market": "A_SHARE",
        "trade_date": date(2026, 6, 1),
        "open": 10.0,
        "high": 10.8,
        "low": 9.8,
        "close": 10.5,
        "pre_close": 10.0,
        "volume": 1000.0,
        "amount": 10500.0,
        "adjust_factor": 1.0,
        "source": "akshare",
    }
    row_000001 = {
        **row_600519,
        "symbol": "000001",
        "exchange": "SZSE",
        "trade_date": date(2026, 6, 2),
    }
    write_daily_bar_partition(repo, date(2026, 6, 1), [row_600519])
    write_daily_bar_partition(repo, date(2026, 6, 2), [row_000001])

    db = SessionLocal()
    try:
        db.add(
            Dataset(
                name="daily_bars",
                layer="silver",
                storage_type="parquet",
                path=str(repo.dataset_dir),
                schema_json={"symbol": "string", "trade_date": "date"},
                primary_keys_json=["symbol", "exchange", "market", "trade_date"],
                partition_keys_json=["market", "trade_date"],
                source="akshare",
                row_count=2,
                latest_data_date=date(2026, 6, 2),
                quality_status="unknown",
            )
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="akshare"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="akshare"),
            ]
        )
        db.commit()

        DataQualityService(db, lake_root=tmp_path / "lake").run_check()
        symbol_report = db.scalar(
            select(DataQualityReport).where(DataQualityReport.check_type == "missing_trade_date_by_symbol")
        )
    finally:
        db.close()

    assert symbol_report is not None
    assert symbol_report.status == "warning"
    assert symbol_report.severity == "warning"
    assert symbol_report.metric_name == "symbols_missing_open_days"
    assert symbol_report.metric_value == "2 symbols / 2 days"
    assert "600519:2026-06-02" in symbol_report.message
    assert "000001:2026-06-01" in symbol_report.message


def test_daily_bars_quality_check_does_not_hide_missing_qfq_days_with_none_rows(client, tmp_path):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    base_row = {
        "symbol": "600519",
        "exchange": "SSE",
        "market": "A_SHARE",
        "open": 10.0,
        "high": 10.8,
        "low": 9.8,
        "close": 10.5,
        "pre_close": 10.0,
        "volume": 1000.0,
        "amount": 10500.0,
        "adjust_factor": 1.0,
        "source": "fixture",
        "ingested_at": datetime(2026, 6, 3, tzinfo=timezone.utc),
    }
    write_daily_bar_partition(
        repo,
        date(2026, 6, 1),
        [
            {**base_row, "trade_date": date(2026, 6, 1), "adjust_type": "none"},
            {**base_row, "trade_date": date(2026, 6, 1), "adjust_type": "qfq"},
        ],
    )
    write_daily_bar_partition(
        repo,
        date(2026, 6, 2),
        [{**base_row, "trade_date": date(2026, 6, 2), "adjust_type": "none"}],
    )

    db = SessionLocal()
    try:
        db.add(
            Dataset(
                name="daily_bars",
                layer="silver",
                storage_type="parquet",
                path=str(repo.dataset_dir),
                schema_json={"symbol": "string", "trade_date": "date", "adjust_type": "string"},
                primary_keys_json=["symbol", "exchange", "market", "trade_date", "adjust_type"],
                partition_keys_json=["market", "trade_date"],
                source="fixture",
                row_count=3,
                latest_data_date=date(2026, 6, 2),
                quality_status="unknown",
            )
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
            ]
        )
        db.commit()

        DataQualityService(db, lake_root=tmp_path / "lake").run_check()
        qfq_report = db.scalar(
            select(DataQualityReport).where(
                DataQualityReport.check_type == "missing_trade_date_by_adjustment",
                DataQualityReport.metric_name == "A_SHARE_qfq_missing_open_days",
            )
        )
    finally:
        db.close()

    assert qfq_report is not None
    assert qfq_report.metric_value == "1"
    assert "qfq" in qfq_report.message
    assert "2026-06-02" in qfq_report.message


def test_daily_bars_quality_check_detects_stock_pool_symbols_without_daily_bars(client, tmp_path):
    repo = DailyBarRepository(lake_root=tmp_path / "lake")
    row_600519 = {
        "symbol": "600519",
        "exchange": "SSE",
        "market": "A_SHARE",
        "trade_date": date(2026, 6, 1),
        "open": 10.0,
        "high": 10.8,
        "low": 9.8,
        "close": 10.5,
        "pre_close": 10.0,
        "volume": 1000.0,
        "amount": 10500.0,
        "adjust_factor": 1.0,
        "source": "akshare",
    }
    write_daily_bar_partition(repo, date(2026, 6, 1), [row_600519])

    db = SessionLocal()
    try:
        db.add(
            Dataset(
                name="daily_bars",
                layer="silver",
                storage_type="parquet",
                path=str(repo.dataset_dir),
                schema_json={"symbol": "string", "trade_date": "date"},
                primary_keys_json=["symbol", "exchange", "market", "trade_date"],
                partition_keys_json=["market", "trade_date"],
                source="akshare",
                row_count=1,
                latest_data_date=date(2026, 6, 1),
                quality_status="unknown",
            )
        )
        db.add_all(
            [
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    industry="白酒",
                    source="fixture",
                ),
                Stock(
                    symbol="000001",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="平安银行",
                    status="LISTED",
                    industry="银行",
                    source="fixture",
                ),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="akshare"),
            ]
        )
        db.commit()

        DataQualityService(db, lake_root=tmp_path / "lake").run_check()
        stock_pool_report = db.scalar(
            select(DataQualityReport).where(DataQualityReport.check_type == "stock_pool_missing_daily_bars")
        )
    finally:
        db.close()

    assert stock_pool_report is not None
    assert stock_pool_report.status == "warning"
    assert stock_pool_report.severity == "warning"
    assert stock_pool_report.metric_name == "A_SHARE_listed_symbols_without_daily_bars"
    assert stock_pool_report.metric_value == "1 symbols / 1 symbol-days"
    assert "000001" in stock_pool_report.message


def write_daily_bar_partition(repo: DailyBarRepository, trade_date: date, rows: list[dict]) -> None:
    partition_dir = repo.dataset_dir / "market=A_SHARE" / f"trade_date={trade_date.isoformat()}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=DAILY_BAR_ARROW_SCHEMA)
    pq.write_table(table, partition_dir / "part-000.parquet")
