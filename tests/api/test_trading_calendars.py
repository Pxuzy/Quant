from __future__ import annotations

from datetime import date

from sqlalchemy import select

from backend.app.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    NormalizedTradingCalendar,
    ProviderMetadata,
    StockDataSourceAdapter,
)
from backend.app.adapters.registry import AdapterRegistry
from backend.app.db.session import SessionLocal
from backend.app.models import Dataset, IngestBatch, RawArtifact, TradingCalendar
from backend.app.services.trading_calendar_service import TradingCalendarService


class FailingCalendarAdapter(StockDataSourceAdapter):
    code = "failing_calendar"
    name = "Failing Calendar"
    priority = 5

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=False, calendars=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str) -> list[dict]:
        return []

    def normalize_stock_list(self, raw_records: list[dict]) -> list[NormalizedStock]:
        return []

    def normalize_daily_bars(self, raw_records: list[dict]) -> list[NormalizedDailyBar]:
        return []

    def fetch_trading_calendar(self, **kwargs) -> list[dict]:
        raise RuntimeError("calendar fetch failed")

    def normalize_trading_calendar(self, raw_records: list[dict], *, market: str) -> list[NormalizedTradingCalendar]:
        return []


class SuccessCalendarAdapter(StockDataSourceAdapter):
    code = "success_calendar"
    name = "Success Calendar"
    priority = 10

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=False, calendars=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str) -> list[dict]:
        return []

    def normalize_stock_list(self, raw_records: list[dict]) -> list[NormalizedStock]:
        return []

    def normalize_daily_bars(self, raw_records: list[dict]) -> list[NormalizedDailyBar]:
        return []

    def fetch_trading_calendar(self, **kwargs) -> list[dict]:
        return [
            {"trade_date": date(2026, 6, 1), "is_open": True},
            {"trade_date": date(2026, 6, 2), "is_open": True},
            {"trade_date": date(2026, 6, 6), "is_open": False},
        ]

    def normalize_trading_calendar(self, raw_records: list[dict], *, market: str) -> list[NormalizedTradingCalendar]:
        return [
            NormalizedTradingCalendar(
                market=market,
                trade_date=record["trade_date"],
                is_open=bool(record["is_open"]),
                source=self.code,
            )
            for record in raw_records
        ]


def seed_calendar_rows() -> None:
    db = SessionLocal()
    try:
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 6), is_open=False, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()


def test_trading_calendar_api_lists_days_with_filters(client):
    seed_calendar_rows()

    response = client.get(
        "/api/trading-calendars",
        params={"market": "A_SHARE", "is_open": True, "page": 1, "page_size": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["market"] == "A_SHARE"
    assert payload["items"][0]["is_open"] is True
    assert payload["items"][0]["source"] == "fixture"


def test_trading_calendar_sync_api_creates_pending_task(client):
    response = client.post(
        "/api/trading-calendars/sync",
        json={
            "source": "auto",
            "market": "A_SHARE",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["task_type"] == "calendars"
    assert payload["source"] == "auto"
    assert payload["market"] == "A_SHARE"
    assert payload["status"] == "pending"


def test_auto_calendar_sync_falls_back_and_updates_catalog(client):
    registry = AdapterRegistry()
    registry.register(FailingCalendarAdapter())
    registry.register(SuccessCalendarAdapter())

    db = SessionLocal()
    try:
        service = TradingCalendarService(db, registry)
        task = service.run_calendar_sync(
            source="auto",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        )
        logs = list(task.logs)
        dataset = db.scalar(select(Dataset).where(Dataset.name == "trading_calendars"))
        rows = db.scalars(select(TradingCalendar).order_by(TradingCalendar.trade_date.asc())).all()
        batches = db.scalars(select(IngestBatch).where(IngestBatch.task_id == task.id)).all()
        artifact = db.get(RawArtifact, batches[0].raw_artifact_id) if batches and batches[0].raw_artifact_id else None
    finally:
        db.close()

    assert task.status == "success"
    assert task.records_read == 3
    assert task.records_written == 3
    assert dataset is not None
    assert dataset.storage_type == "postgres"
    assert dataset.source == "success_calendar"
    assert dataset.row_count == 3
    assert dataset.latest_data_date == date(2026, 6, 6)
    assert len(batches) == 1
    assert batches[0].dataset_name == "trading_calendars"
    assert batches[0].requested_source == "auto"
    assert batches[0].source == "success_calendar"
    assert batches[0].status == "success"
    assert batches[0].raw_records == 3
    assert batches[0].normalized_records == 3
    assert batches[0].records_written == 3
    assert batches[0].raw_artifact_id is not None
    assert artifact is not None
    assert artifact.source == "success_calendar"
    assert artifact.row_count == 3
    assert [row.is_open for row in rows] == [True, True, False]
    assert any(
        log.message == "Provider attempt failed." and log.payload_json["source"] == "failing_calendar" for log in logs
    )
    assert any(
        log.message == "Trading calendar sync completed." and log.payload_json["selected_source"] == "success_calendar"
        for log in logs
    )


def test_auto_calendar_sync_reports_all_failures(client):
    registry = AdapterRegistry()
    registry.register(FailingCalendarAdapter())

    db = SessionLocal()
    try:
        service = TradingCalendarService(db, registry)
        task = service.run_calendar_sync(
            source="auto",
            market="A_SHARE",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 6),
        )
        logs = list(task.logs)
    finally:
        db.close()

    assert task.status == "failed"
    assert task.error_message == "All calendar data sources failed: failing_calendar: calendar fetch failed"
    assert any(log.message == "Provider attempt failed." for log in logs)
    assert any(log.message == "Trading calendar sync failed." for log in logs)
