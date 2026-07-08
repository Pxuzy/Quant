from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from backend.app.adapters.base import NormalizedDailyBar
from backend.app.core.config import get_settings
from backend.app.models import IngestBatch, Stock, SyncTask, TradingCalendar
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.worker.sync_stocks import run_next_pending_stock_sync


def install_fake_akshare(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(
            stock_info_a_code_name=lambda: [
                {"code": "600519", "name": "Kweichow Moutai", "listing_date": "2001-08-27"},
                {"code": "000001", "name": "Ping An Bank", "listing_date": "1991-04-03"},
                {"code": "601318", "name": "Ping An Insurance", "listing_date": "2007-03-01"},
                {"code": "300750", "name": "CATL", "listing_date": "2018-06-11"},
                {"code": "688981", "name": "SMIC", "listing_date": "2020-07-16"},
                {"code": "430047", "name": "NQ Technology", "listing_date": "2014-01-24"},
                {"code": "000002", "name": "Vanke A", "listing_date": "1991-01-29"},
                {"code": "600001", "name": "Legacy Industrial", "listing_date": "1990-12-19"},
            ]
        ),
    )


def make_daily_bar(
    *,
    symbol: str = "600519",
    exchange: str = "SSE",
    market: str = "A_SHARE",
    trade_date: date,
    open: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 1000.0,
    amount: float = 100500.0,
    adjust_type: str = "none",
) -> NormalizedDailyBar:
    return NormalizedDailyBar(
        symbol=symbol,
        exchange=exchange,
        market=market,
        trade_date=trade_date,
        open=open,
        high=high,
        low=low,
        close=close,
        pre_close=None,
        volume=volume,
        amount=amount,
        adjust_factor=1.0,
        source="fixture",
        adjust_type=adjust_type,
    )


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cors_allows_local_frontend_dev_origins(client):
    for origin in ("http://127.0.0.1:5173", "http://localhost:5173"):
        response = client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_stock_sync_and_server_side_pagination(client, monkeypatch):
    install_fake_akshare(monkeypatch)

    sync_response = client.post("/api/stocks/sync", json={})

    assert sync_response.status_code == 201
    task = sync_response.json()
    assert task["status"] == "pending"
    assert task["records_read"] == 0
    assert task["records_written"] == 0

    page_response = client.get("/api/stocks", params={"page": 1, "page_size": 2})
    assert page_response.status_code == 200
    page = page_response.json()
    assert page["page"] == 1
    assert page["page_size"] == 2
    assert page["total"] == 0
    assert page["items"] == []

    executed_task = run_next_pending_stock_sync()
    assert executed_task is not None
    assert executed_task.status == "success"
    assert executed_task.records_written >= 8

    page_response = client.get("/api/stocks", params={"page": 1, "page_size": 2})
    assert page_response.status_code == 200
    page = page_response.json()
    assert page["total"] >= 8
    assert len(page["items"]) == 2

    keyword_response = client.get("/api/stocks", params={"keyword": "Moutai", "page_size": 20})
    assert keyword_response.status_code == 200
    keyword_page = keyword_response.json()
    assert keyword_page["total"] == 1
    assert keyword_page["items"][0]["symbol"] == "600519"

    detail_response = client.get("/api/stocks/600519", params={"market": "A_SHARE"})
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["symbol"] == "600519"
    assert detail["market"] == "A_SHARE"

    status_response = client.get("/api/stocks", params={"status": "LISTED", "page_size": 20})
    assert status_response.status_code == 200
    status_page = status_response.json()
    assert status_page["total"] >= 8
    assert status_page["items"][0]["status"] == "LISTED"


def test_stock_list_includes_latest_data_date_and_completeness(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    from backend.app.db.session import SessionLocal

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
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
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

    response = client.get("/api/stocks", params={"market": "A_SHARE", "page": 1, "page_size": 20})

    assert response.status_code == 200
    items_by_symbol = {item["symbol"]: item for item in response.json()["items"]}
    assert items_by_symbol["600519"]["latest_data_date"] == "2026-06-03"
    assert items_by_symbol["600519"]["data_completeness"] == 0.6667
    assert items_by_symbol["000001"]["latest_data_date"] is None
    assert items_by_symbol["000001"]["data_completeness"] is None


def test_stock_list_filters_by_exchange_industry_and_daily_coverage(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    from backend.app.db.session import SessionLocal

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
                Stock(
                    symbol="300750",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="宁德时代",
                    status="LISTED",
                    industry="电池",
                    listing_date=date(2018, 6, 11),
                    source="fixture",
                ),
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 3), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    DailyBarRepository(lake_root=lake_root).write_many(
        [
            make_daily_bar(symbol="600519", exchange="SSE", trade_date=date(2026, 6, 1)),
            make_daily_bar(symbol="600519", exchange="SSE", trade_date=date(2026, 6, 3)),
            make_daily_bar(symbol="300750", exchange="SZSE", trade_date=date(2026, 6, 1)),
            make_daily_bar(symbol="300750", exchange="SZSE", trade_date=date(2026, 6, 2)),
            make_daily_bar(symbol="300750", exchange="SZSE", trade_date=date(2026, 6, 3)),
        ]
    )

    exchange_response = client.get("/api/stocks", params={"exchange": "SSE", "page_size": 20})
    assert exchange_response.status_code == 200
    assert [item["symbol"] for item in exchange_response.json()["items"]] == ["600519"]

    industry_response = client.get("/api/stocks", params={"industry": "银行", "page_size": 20})
    assert industry_response.status_code == 200
    assert [item["symbol"] for item in industry_response.json()["items"]] == ["000001"]

    missing_response = client.get("/api/stocks", params={"daily_coverage": "missing", "page_size": 20})
    assert missing_response.status_code == 200
    assert [item["symbol"] for item in missing_response.json()["items"]] == ["000001"]

    repair_response = client.get("/api/stocks", params={"daily_coverage": "needs_repair", "page_size": 20})
    assert repair_response.status_code == 200
    assert [item["symbol"] for item in repair_response.json()["items"]] == ["600519"]

    complete_response = client.get("/api/stocks", params={"daily_coverage": "complete", "page_size": 20})
    assert complete_response.status_code == 200
    assert [item["symbol"] for item in complete_response.json()["items"]] == ["300750"]


def test_stock_daily_coverage_reports_missing_trade_dates(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            Stock(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                name="贵州茅台",
                status="LISTED",
                industry="白酒",
                listing_date=date(2001, 8, 27),
                source="fixture",
            )
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
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

    response = client.get("/api/stocks/600519/daily-coverage", params={"market": "A_SHARE"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["first_data_date"] == "2026-06-01"
    assert payload["latest_data_date"] == "2026-06-03"
    assert payload["expected_trade_days"] == 3
    assert payload["actual_trade_days"] == 2
    assert payload["missing_trade_days"] == 1
    assert payload["data_completeness"] == 0.6667
    assert payload["missing_trade_date_samples"] == ["2026-06-02"]


def test_stock_daily_quality_summarizes_backend_quality_issues(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            Stock(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                name="贵州茅台",
                status="LISTED",
                industry="白酒",
                listing_date=date(2001, 8, 27),
                source="fixture",
            )
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 3), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    DailyBarRepository(lake_root=lake_root).write_many(
        [
            make_daily_bar(trade_date=date(2026, 6, 1)),
            make_daily_bar(
                trade_date=date(2026, 6, 3),
                open=101.0,
                high=100.0,
                low=102.0,
                close=101.5,
                volume=-1200.0,
                amount=-121800.0,
            ),
        ]
    )

    response = client.get("/api/stocks/600519/daily-quality", params={"market": "A_SHARE"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["status"] == "error"
    assert payload["checked_rows"] == 2
    assert payload["first_data_date"] == "2026-06-01"
    assert payload["latest_data_date"] == "2026-06-03"
    assert payload["expected_trade_days"] == 3
    assert payload["actual_trade_days"] == 2
    assert payload["missing_trade_days"] == 1
    assert payload["data_completeness"] == 0.6667
    assert payload["missing_trade_date_samples"] == ["2026-06-02"]
    assert payload["duplicate_daily_keys"] == 0
    assert payload["ohlc_error_count"] == 1
    assert payload["negative_price_count"] == 0
    assert payload["negative_volume_count"] == 1
    assert payload["negative_amount_count"] == 1


def test_stock_daily_quality_treats_adjust_types_as_distinct_rows(client, tmp_path, monkeypatch):
    lake_root = tmp_path / "lake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake_root))
    get_settings.cache_clear()

    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            Stock(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                name="贵州茅台",
                status="LISTED",
                industry="白酒",
                listing_date=date(2001, 8, 27),
                source="fixture",
            )
        )
        db.add(TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"))
        db.commit()
    finally:
        db.close()

    DailyBarRepository(lake_root=lake_root).write_many(
        [
            make_daily_bar(trade_date=date(2026, 6, 1), adjust_type="none"),
            make_daily_bar(trade_date=date(2026, 6, 1), high=102.0, close=101.5, adjust_type="qfq"),
        ]
    )

    response = client.get("/api/stocks/600519/daily-quality", params={"market": "A_SHARE"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "good"
    assert payload["checked_rows"] == 2
    assert payload["actual_trade_days"] == 1
    assert payload["duplicate_daily_keys"] == 0
    assert payload["missing_trade_days"] == 0


def test_stock_daily_quality_returns_unknown_without_daily_bars(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    get_settings.cache_clear()

    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            Stock(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                name="贵州茅台",
                status="LISTED",
                industry="白酒",
                listing_date=date(2001, 8, 27),
                source="fixture",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/stocks/600519/daily-quality", params={"market": "A_SHARE"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["status"] == "unknown"
    assert payload["checked_rows"] == 0
    assert payload["first_data_date"] is None
    assert payload["latest_data_date"] is None
    assert payload["missing_trade_days"] == 0


def test_stock_daily_ingest_batches_returns_recent_symbol_batches(client):
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            Stock(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                name="贵州茅台",
                status="LISTED",
                industry="白酒",
                listing_date=date(2001, 8, 27),
                source="fixture",
            )
        )
        task = SyncTask(
            task_type="daily_bars",
            source="auto",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 3),
            status="success",
            progress=100,
            records_read=3,
            records_written=3,
        )
        db.add(task)
        db.flush()
        db.add_all(
            [
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="akshare",
                    requested_source="auto",
                    market="A_SHARE",
                    symbol="600519",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 3),
                    status="success",
                    schema_version="v1",
                    normalize_version="v2",
                    raw_records=3,
                    normalized_records=3,
                    records_written=3,
                    validation_errors_json=[],
                    quality_status="good",
                ),
                IngestBatch(
                    task_id=task.id,
                    dataset_name="daily_bars",
                    source="baostock",
                    requested_source="baostock",
                    market="A_SHARE",
                    symbol="000001",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 3),
                    status="success",
                    schema_version="v1",
                    normalize_version="v1",
                    raw_records=3,
                    normalized_records=3,
                    records_written=3,
                    validation_errors_json=[],
                    quality_status="good",
                ),
                IngestBatch(
                    task_id=task.id,
                    dataset_name="stocks",
                    source="akshare",
                    requested_source="auto",
                    market="A_SHARE",
                    symbol="600519",
                    status="success",
                    schema_version="v1",
                    normalize_version="v1",
                    raw_records=1,
                    normalized_records=1,
                    records_written=1,
                    validation_errors_json=[],
                    quality_status="good",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/stocks/600519/daily-ingest-batches", params={"market": "A_SHARE"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "600519"
    assert payload["market"] == "A_SHARE"
    assert payload["total"] == 1
    batch = payload["items"][0]
    assert batch["task_id"] == task.id
    assert batch["dataset_name"] == "daily_bars"
    assert batch["source"] == "akshare"
    assert batch["requested_source"] == "auto"
    assert batch["start_date"] == "2026-06-01"
    assert batch["end_date"] == "2026-06-03"
    assert batch["schema_version"] == "v1"
    assert batch["normalize_version"] == "v2"
    assert batch["records_written"] == 3
    assert batch["quality_status"] == "good"


def test_stock_detail_returns_404_for_missing_symbol(client):
    response = client.get("/api/stocks/999999")

    assert response.status_code == 404


def test_stock_detail_prefers_common_a_share_row_when_symbol_is_duplicated(client):
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="000001",
                    exchange="SSE",
                    market="A_SHARE",
                    name="上海综合指数",
                    status="LISTED",
                    industry="指数",
                    listing_date=date(1990, 12, 19),
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
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/stocks/000001", params={"market": "A_SHARE"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["exchange"] == "SZSE"
    assert payload["name"] == "平安银行"


def test_sync_tasks_api_returns_created_sync(client):
    client.post("/api/stocks/sync", json={"source": "auto", "market": "A_SHARE"})

    response = client.get("/api/sync-tasks", params={"status": "pending"})

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 1
    assert page["items"][0]["task_type"] == "stock_list"
    assert page["items"][0]["source"] == "auto"


def test_sync_task_detail_and_logs(client, monkeypatch):
    install_fake_akshare(monkeypatch)

    sync_response = client.post("/api/stocks/sync", json={"source": "auto", "market": "A_SHARE"})
    task = sync_response.json()

    detail_response = client.get(f"/api/sync-tasks/{task['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == task["id"]
    assert detail["status"] == "pending"
    assert detail["records_written"] == 0

    executed_task = run_next_pending_stock_sync()
    assert executed_task is not None

    detail_response = client.get(f"/api/sync-tasks/{task['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "success"
    assert detail["records_written"] >= 8

    logs_response = client.get(f"/api/sync-tasks/{task['id']}/logs")
    assert logs_response.status_code == 200
    logs_page = logs_response.json()
    assert logs_page["task_id"] == task["id"]
    assert logs_page["total"] >= 4
    assert logs_page["total"] == len(logs_page["items"])

    log_ids = [item["id"] for item in logs_page["items"]]
    assert log_ids == sorted(log_ids)
    assert logs_page["items"][0]["message"] == "Stock list sync task created."
    assert logs_page["items"][-1]["message"] == "Stock list sync completed."

    batches_response = client.get(f"/api/sync-tasks/{task['id']}/ingest-batches")
    assert batches_response.status_code == 200
    batches_page = batches_response.json()
    assert batches_page["task_id"] == task["id"]
    assert batches_page["total"] == 1
    batch = batches_page["items"][0]
    assert batch["dataset_name"] == "stocks"
    assert batch["requested_source"] == "auto"
    assert batch["source"] == "akshare"
    assert batch["status"] == "success"
    assert batch["raw_records"] >= 8
    assert batch["normalized_records"] >= 8
    assert batch["records_written"] >= 8
    assert batch["validation_errors_json"] == []


def test_sync_task_detail_and_logs_return_404_for_missing_task(client):
    detail_response = client.get("/api/sync-tasks/999999")
    logs_response = client.get("/api/sync-tasks/999999/logs")
    batches_response = client.get("/api/sync-tasks/999999/ingest-batches")

    assert detail_response.status_code == 404
    assert logs_response.status_code == 404
    assert batches_response.status_code == 404
