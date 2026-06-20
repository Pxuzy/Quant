from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from apps.api.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    ProviderMetadata,
    StockDataSourceAdapter,
)
from apps.api.adapters.registry import AdapterRegistry
from apps.api.db.session import SessionLocal
from apps.api.models import Dataset, IngestBatch, Stock, SyncTask, TradingCalendar
from apps.api.services.market_data_query_service import MarketDataQueryService
from apps.api.services.market_data_sync_service import MarketDataSyncService


class FailingDailyBarAdapter(StockDataSourceAdapter):
    code = "failing_daily"
    name = "Failing Daily"
    priority = 5

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=False, daily_bars=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str) -> list[dict]:
        return []

    def normalize_stock_list(self, raw_records: list[dict]) -> list[NormalizedStock]:
        return []

    def fetch_daily_bars(self, **kwargs) -> list[dict]:
        raise RuntimeError("daily fetch failed")

    def normalize_daily_bars(self, raw_records: list[dict]) -> list[NormalizedDailyBar]:
        return []


class SuccessDailyBarAdapter(StockDataSourceAdapter):
    code = "success_daily"
    name = "Success Daily"
    priority = 10

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=False, daily_bars=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str) -> list[dict]:
        return []

    def normalize_stock_list(self, raw_records: list[dict]) -> list[NormalizedStock]:
        return []

    def fetch_daily_bars(self, **kwargs) -> list[dict]:
        return [
            {"trade_date": date(2026, 6, 1), "close": 1675.0},
            {"trade_date": date(2026, 6, 2), "close": 1688.0},
        ]

    def normalize_daily_bars(self, raw_records: list[dict]) -> list[NormalizedDailyBar]:
        return [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=record["trade_date"],
                open=record["close"] - 10.0,
                high=record["close"] + 5.0,
                low=record["close"] - 15.0,
                close=record["close"],
                pre_close=None,
                volume=1000.0,
                amount=record["close"] * 1000,
                adjust_factor=1.0,
                source=self.code,
            )
            for record in raw_records
        ]


class InvalidDailyBarAdapter(SuccessDailyBarAdapter):
    code = "invalid_daily"
    name = "Invalid Daily"

    def normalize_daily_bars(self, raw_records: list[dict]) -> list[NormalizedDailyBar]:
        return [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=date(2026, 6, 1),
                open=100.0,
                high=90.0,
                low=95.0,
                close=98.0,
                pre_close=None,
                volume=1000.0,
                amount=98000.0,
                adjust_factor=1.0,
                source=self.code,
            )
        ]


class MultiSymbolDailyBarAdapter(SuccessDailyBarAdapter):
    code = "multi_symbol_daily"
    name = "Multi Symbol Daily"

    def fetch_daily_bars(self, **kwargs) -> list[dict]:
        symbol = kwargs["symbol"]
        return [
            {"symbol": symbol, "trade_date": date(2026, 6, 1), "close": 10.0 if symbol == "000001" else 20.0},
            {"symbol": symbol, "trade_date": date(2026, 6, 2), "close": 11.0 if symbol == "000001" else 21.0},
        ]

    def normalize_daily_bars(self, raw_records: list[dict]) -> list[NormalizedDailyBar]:
        return [
            NormalizedDailyBar(
                symbol=record["symbol"],
                exchange="SZSE" if record["symbol"].startswith("0") else "SSE",
                market="A_SHARE",
                trade_date=record["trade_date"],
                open=record["close"] - 0.5,
                high=record["close"] + 0.5,
                low=record["close"] - 1.0,
                close=record["close"],
                pre_close=None,
                volume=1000.0,
                amount=record["close"] * 1000,
                adjust_factor=1.0,
                source=self.code,
            )
            for record in raw_records
        ]


class FailsFirstSymbolDailyBarAdapter(MultiSymbolDailyBarAdapter):
    code = "fails_first_symbol_daily"
    name = "Fails First Symbol Daily"

    def fetch_daily_bars(self, **kwargs) -> list[dict]:
        if kwargs["symbol"] == "920000":
            raise RuntimeError("股票代码未标识sh或sz")
        return super().fetch_daily_bars(**kwargs)


def test_daily_bars_sync_api_creates_pending_task(client):
    response = client.post(
        "/api/market-data/daily-bars/sync",
        json={
            "source": "auto",
            "market": "A_SHARE",
            "symbol": "600519",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_type"] == "daily_bars"
    assert payload["source"] == "auto"
    assert payload["symbol"] == "600519"
    assert payload["status"] == "pending"


def test_market_daily_bars_repair_api_creates_explicit_market_task(client):
    response = client.post(
        "/api/market-data/daily-bars/market-repair",
        json={
            "source": "auto",
            "market": "A_SHARE",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
            "max_symbols": 2,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_type"] == "daily_bars_market_repair"
    assert payload["source"] == "auto"
    assert payload["market"] == "A_SHARE"
    assert payload["symbol"] is None
    assert payload["start_date"] == "2026-06-01"
    assert payload["end_date"] == "2026-06-02"
    assert payload["status"] == "pending"


def test_market_daily_bars_repair_preview_does_not_create_sync_task(client, monkeypatch):
    registry = AdapterRegistry()
    registry.register(MultiSymbolDailyBarAdapter())
    monkeypatch.setattr("apps.api.services.market_data_sync_service.default_adapter_registry", lambda: registry)

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="000001",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="Ping An Bank",
                    status="LISTED",
                    industry="Banking",
                    source="fixture",
                ),
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="Kweichow Moutai",
                    status="LISTED",
                    industry="Liquor",
                    source="fixture",
                ),
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2099, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2099, 6, 2), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/market-data/daily-bars/market-repair/preview",
        json={
            "source": "auto",
            "market": "A_SHARE",
            "start_date": "2099-06-01",
            "end_date": "2099-06-02",
            "max_symbols": 2,
        },
    )

    db = SessionLocal()
    try:
        task_count = db.query(SyncTask).count()
    finally:
        db.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "auto"
    assert payload["selected_source"] == "multi_symbol_daily"
    assert payload["candidate_sources"] == ["multi_symbol_daily"]
    assert payload["market"] == "A_SHARE"
    assert payload["stock_pool_count"] == 2
    assert payload["open_dates_count"] == 2
    assert payload["planned_symbols"] == 2
    assert payload["planned_missing_symbol_days"] == 4
    assert len(payload["sample_items"]) == 2
    assert task_count == 0


def test_market_daily_bars_repair_preview_limits_plan_by_max_symbols(client, monkeypatch):
    registry = AdapterRegistry()
    registry.register(MultiSymbolDailyBarAdapter())
    monkeypatch.setattr("apps.api.services.market_data_sync_service.default_adapter_registry", lambda: registry)

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="000001",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="Ping An Bank",
                    status="LISTED",
                    industry="Banking",
                    source="fixture",
                ),
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="Kweichow Moutai",
                    status="LISTED",
                    industry="Liquor",
                    source="fixture",
                ),
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2099, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2099, 6, 2), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/market-data/daily-bars/market-repair/preview",
        json={
            "source": "auto",
            "market": "A_SHARE",
            "start_date": "2099-06-01",
            "end_date": "2099-06-02",
            "max_symbols": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_pool_count"] == 2
    assert payload["planned_symbols"] == 1
    assert payload["planned_missing_symbol_days"] == 2
    assert len(payload["sample_items"]) == 1
    assert payload["sample_items"][0]["symbol"] == "600519"


def test_market_daily_bars_repair_preview_skips_a_share_index_rows(client, monkeypatch):
    registry = AdapterRegistry()
    registry.register(MultiSymbolDailyBarAdapter())
    monkeypatch.setattr("apps.api.services.market_data_sync_service.default_adapter_registry", lambda: registry)

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="000003",
                    exchange="SSE",
                    market="A_SHARE",
                    name="上证B股指数",
                    status="LISTED",
                    source="fixture",
                ),
                Stock(
                    symbol="000001",
                    exchange="SZSE",
                    market="A_SHARE",
                    name="平安银行",
                    status="LISTED",
                    source="fixture",
                ),
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    source="fixture",
                ),
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2099, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2099, 6, 2), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/market-data/daily-bars/market-repair/preview",
        json={
            "source": "auto",
            "market": "A_SHARE",
            "start_date": "2099-06-01",
            "end_date": "2099-06-02",
            "max_symbols": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_pool_count"] == 2
    assert {item["symbol"] for item in payload["sample_items"]} == {"000001", "600519"}


def test_daily_bars_sync_rejects_blank_symbol_without_creating_task(client, tmp_path):
    registry = AdapterRegistry()
    registry.register(SuccessDailyBarAdapter())

    db = SessionLocal()
    try:
        service = MarketDataSyncService(db, registry, lake_root=tmp_path / "lake")
        with pytest.raises(ValueError, match="单只股票"):
            service.create_daily_bars_sync_task(
                source="success_daily",
                market="A_SHARE",
                symbol="   ",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 2),
            )
        tasks = db.scalars(select(SyncTask).where(SyncTask.task_type == "daily_bars")).all()
    finally:
        db.close()

    assert tasks == []


def test_market_daily_bars_repair_rejects_service_limit_above_api_cap(client, tmp_path):
    registry = AdapterRegistry()

    db = SessionLocal()
    try:
        service = MarketDataSyncService(db, registry, lake_root=tmp_path / "lake")
        with pytest.raises(ValueError, match="max_symbols"):
            service.create_market_daily_bars_repair_task(
                source="auto",
                market="A_SHARE",
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 2),
                max_symbols=201,
            )
        tasks = db.scalars(select(SyncTask).where(SyncTask.task_type == "daily_bars_market_repair")).all()
    finally:
        db.close()

    assert tasks == []


def test_market_daily_bars_repair_expands_stock_pool_and_writes_per_symbol_batches(client, tmp_path):
    registry = AdapterRegistry()
    registry.register(MultiSymbolDailyBarAdapter())

    db = SessionLocal()
    try:
        db.add_all(
            [
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
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    industry="白酒",
                    source="fixture",
                ),
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
            ]
        )
        db.commit()

        service = MarketDataSyncService(db, registry, lake_root=tmp_path / "lake")
        task = service.run_market_daily_bars_repair(
            source="multi_symbol_daily",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            max_symbols=2,
        )
        batches = db.scalars(select(IngestBatch).where(IngestBatch.task_id == task.id).order_by(IngestBatch.symbol)).all()
    finally:
        db.close()

    query = MarketDataQueryService(lake_root=tmp_path / "lake").list_daily_bars(
        symbol=None,
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
        page=1,
        page_size=10,
    )

    assert task.task_type == "daily_bars_market_repair"
    assert task.symbol is None
    assert task.status == "success"
    assert task.records_read == 4
    assert task.records_written == 4
    assert [batch.symbol for batch in batches] == ["000001", "600519"]
    assert all(batch.dataset_name == "daily_bars" for batch in batches)
    assert all(batch.source == "multi_symbol_daily" for batch in batches)
    assert all(batch.requested_source == "multi_symbol_daily" for batch in batches)
    assert all(batch.status == "success" for batch in batches)
    assert query["total"] == 4
    assert {item["symbol"] for item in query["items"]} == {"000001", "600519"}


def test_market_daily_bars_repair_skips_failed_symbol_and_continues(client, tmp_path):
    registry = AdapterRegistry()
    registry.register(FailsFirstSymbolDailyBarAdapter())

    db = SessionLocal()
    try:
        db.add_all(
            [
                Stock(
                    symbol="920000",
                    exchange="BSE",
                    market="A_SHARE",
                    name="安徽凤凰",
                    status="LISTED",
                    industry=None,
                    source="fixture",
                ),
                Stock(
                    symbol="600519",
                    exchange="SSE",
                    market="A_SHARE",
                    name="贵州茅台",
                    status="LISTED",
                    industry="白酒",
                    source="fixture",
                ),
            ]
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
            ]
        )
        db.commit()

        service = MarketDataSyncService(db, registry, lake_root=tmp_path / "lake")
        task = service.run_market_daily_bars_repair(
            source="fails_first_symbol_daily",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            max_symbols=2,
        )
        log_messages = [log.message for log in task.logs]
        batches = db.scalars(select(IngestBatch).where(IngestBatch.task_id == task.id).order_by(IngestBatch.symbol)).all()
    finally:
        db.close()

    query = MarketDataQueryService(lake_root=tmp_path / "lake").list_daily_bars(
        symbol=None,
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
        page=1,
        page_size=10,
    )

    assert task.status == "success"
    assert task.records_read == 2
    assert task.records_written == 2
    assert "Market repair symbol failed." in log_messages
    assert [batch.symbol for batch in batches] == ["600519", "920000"]
    batches_by_symbol = {batch.symbol: batch for batch in batches}
    assert batches_by_symbol["600519"].status == "success"
    assert batches_by_symbol["920000"].status == "failed"
    assert batches_by_symbol["920000"].raw_records == 0
    assert batches_by_symbol["920000"].normalized_records == 0
    assert batches_by_symbol["920000"].records_written == 0
    assert "股票代码未标识sh或sz" in (batches_by_symbol["920000"].error_message or "")
    assert query["total"] == 2
    assert {item["symbol"] for item in query["items"]} == {"600519"}


def test_auto_daily_bars_sync_falls_back_and_writes_parquet(client, tmp_path):
    registry = AdapterRegistry()
    registry.register(FailingDailyBarAdapter())
    registry.register(SuccessDailyBarAdapter())

    db = SessionLocal()
    try:
        service = MarketDataSyncService(db, registry, lake_root=tmp_path / "lake")
        task = service.run_daily_bars_sync(
            source="auto",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
        )
        logs = list(task.logs)
        dataset = db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        batches = db.scalars(select(IngestBatch).where(IngestBatch.task_id == task.id).order_by(IngestBatch.id)).all()
    finally:
        db.close()

    query = MarketDataQueryService(lake_root=tmp_path / "lake").list_daily_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
        page=1,
        page_size=10,
    )

    assert task.status == "success"
    assert task.records_read == 2
    assert task.records_written == 2
    assert dataset is not None
    assert dataset.storage_type == "parquet"
    assert dataset.source == "success_daily"
    assert dataset.row_count == 2
    assert dataset.latest_data_date == date(2026, 6, 2)
    assert len(batches) == 1
    assert batches[0].dataset_name == "daily_bars"
    assert batches[0].requested_source == "auto"
    assert batches[0].source == "success_daily"
    assert batches[0].status == "success"
    assert batches[0].raw_records == 2
    assert batches[0].normalized_records == 2
    assert batches[0].records_written == 2
    assert batches[0].validation_errors_json == []
    assert query["total"] == 2
    assert query["items"][0]["symbol"] == "600519"
    assert query["items"][0]["source"] == "success_daily"
    assert query["items"][0]["adjust_type"] == "none"
    assert query["items"][0]["ingested_at"] is not None
    assert any(log.message == "Provider attempt failed." and log.payload_json["source"] == "failing_daily" for log in logs)
    assert any(
        log.message == "Daily bars sync completed." and log.payload_json["selected_source"] == "success_daily"
        for log in logs
    )


def test_daily_bars_query_can_return_latest_rows_first(client, tmp_path):
    registry = AdapterRegistry()
    registry.register(SuccessDailyBarAdapter())

    db = SessionLocal()
    try:
        service = MarketDataSyncService(db, registry, lake_root=tmp_path / "lake")
        service.run_daily_bars_sync(
            source="success_daily",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
        )
    finally:
        db.close()

    query = MarketDataQueryService(lake_root=tmp_path / "lake").list_daily_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=None,
        end_date=None,
        page=1,
        page_size=1,
        sort_order="desc",
    )

    assert query["total"] == 2
    assert query["items"][0]["trade_date"] == date(2026, 6, 2)
    assert query["items"][0]["close"] == 1688.0


def test_daily_bars_schema_validation_failure_creates_failed_ingest_batch(client, tmp_path):
    registry = AdapterRegistry()
    registry.register(InvalidDailyBarAdapter())

    db = SessionLocal()
    try:
        service = MarketDataSyncService(db, registry, lake_root=tmp_path / "lake")
        task = service.run_daily_bars_sync(
            source="invalid_daily",
            market="A_SHARE",
            symbol="600519",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 1),
        )
        dataset = db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
        batches = db.scalars(select(IngestBatch).where(IngestBatch.task_id == task.id)).all()
    finally:
        db.close()

    query = MarketDataQueryService(lake_root=tmp_path / "lake").list_daily_bars(
        symbol="600519",
        market="A_SHARE",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
        page=1,
        page_size=10,
    )

    assert task.status == "failed"
    assert task.records_written == 0
    assert dataset is None
    assert query["total"] == 0
    assert len(batches) == 1
    assert batches[0].status == "failed"
    assert batches[0].source == "invalid_daily"
    assert batches[0].records_written == 0
    assert any("high" in error for error in batches[0].validation_errors_json)
