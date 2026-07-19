from __future__ import annotations

from datetime import date

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
from backend.app.models import DataSource, Dataset, IngestBatch, Stock, SyncTask
from backend.app.services.data_source_service import DataSourceService
from backend.app.services.stock_sync_service import StockSyncService


class EmptyNormalizeAdapter(StockDataSourceAdapter):
    code = "empty_normalize"
    name = "Empty Normalize"
    priority = 15

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str):
        return [{"symbol": "600519", "exchange": "SSE", "name": "Kweichow Moutai"}]

    def normalize_stock_list(self, raw_records):
        return []



def test_stock_sync_records_normalization_loss_in_ingest_batch(client):
    registry = AdapterRegistry()
    registry.register(EmptyNormalizeAdapter())
    db = SessionLocal()
    try:
        task = StockSyncService(db, registry).run_stock_sync(source="empty_normalize", market="A_SHARE")
        batch = db.query(IngestBatch).filter(IngestBatch.task_id == task.id).one()
    finally:
        db.close()

    assert task.status == "failed"
    assert task.records_read == 0
    assert task.records_written == 0
    assert batch.raw_records == 1
    assert batch.normalized_records == 0
    assert batch.dropped_records == 1
    assert batch.status == "failed"
    assert batch.quality_status == "failed"


class FailingFetchAdapter(StockDataSourceAdapter):
    code = "failing_fetch"
    name = "Failing Fetch"
    priority = 5

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str):
        raise RuntimeError("fetch failed")

    def normalize_stock_list(self, raw_records):
        return []


class LeakyFetchAdapter(StockDataSourceAdapter):
    code = "leaky_fetch"
    name = "Leaky Fetch"
    priority = 6

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str):
        raise RuntimeError(
            "upstream failed at https://secret.example.test/path?a=1 through hidden.example.test "
            + ("x" * 800)
        )

    def normalize_stock_list(self, raw_records):
        return []


class NetworkUnavailableAdapter(StockDataSourceAdapter):
    code = "network_unavailable"
    name = "Network Unavailable"
    priority = 7

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=False, daily_bars=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="package is available")

    def fetch_daily_bars(self, **kwargs):
        raise RuntimeError(
            "stock-sdk request failed; code=NETWORK_ERROR; provider=eastmoney; "
            "message=fetch failed; url=https://91.push2his.eastmoney.com/api/qt/stock/kline/get"
        )

    def normalize_daily_bars(self, raw_records):
        return []

    def fetch_stock_list(self, *, market: str):
        return []

    def normalize_stock_list(self, raw_records):
        return []


class SuccessOpenProviderAdapter(StockDataSourceAdapter):
    code = "success_open_provider"
    name = "Success Open Provider"
    priority = 10

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=True)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(provider_type="test_fixture", stability="test")

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=True, status="healthy", message="ok")

    def fetch_stock_list(self, *, market: str):
        return [
            {"symbol": "600519", "exchange": "SSE", "name": "贵州茅台"},
            {"symbol": "000001", "exchange": "SZSE", "name": "平安银行"},
        ]

    def normalize_stock_list(self, raw_records):
        return [
            NormalizedStock(
                symbol=str(record["symbol"]),
                exchange=str(record["exchange"]),
                market="A_SHARE",
                name=str(record["name"]),
                status="LISTED",
                industry=None,
                listing_date=date(2001, 1, 1),
                delisting_date=None,
                source=self.code,
            )
            for record in raw_records
        ]


class WriteDuringFetchProviderAdapter(SuccessOpenProviderAdapter):
    code = "write_during_fetch_provider"
    name = "Write During Fetch Provider"

    def fetch_stock_list(self, *, market: str):
        db = SessionLocal()
        try:
            db.add(
                DataSource(
                    code="write_during_fetch_probe",
                    name="Write During Fetch Probe",
                    enabled=True,
                    priority=99,
                    requires_token=False,
                    config_json={"purpose": "prove smoke fetch does not hold a write transaction"},
                )
            )
            db.commit()
        finally:
            db.close()
        return super().fetch_stock_list(market=market)


class MixedSecurityProviderAdapter(SuccessOpenProviderAdapter):
    code = "mixed_security_provider"
    name = "Mixed Security Provider"

    def fetch_stock_list(self, *, market: str):
        return [
            {"symbol": "600519", "exchange": "SSE", "name": "贵州茅台", "status": "LISTED"},
            {"symbol": "000001", "exchange": "SZSE", "name": "平安银行", "status": "LISTED"},
            {"symbol": "430047", "exchange": "BSE", "name": "北交所样本", "status": "LISTED"},
            {"symbol": "000016", "exchange": "SSE", "name": "上证50指数", "status": "LISTED"},
            {"symbol": "159001", "exchange": "SZSE", "name": "货币ETF", "status": "LISTED"},
            {"symbol": "123001", "exchange": "SZSE", "name": "可转债样本", "status": "LISTED"},
            {"symbol": "600001", "exchange": "SSE", "name": "退市样本", "status": "DELISTED"},
        ]

    def normalize_stock_list(self, raw_records):
        return [
            NormalizedStock(
                symbol=str(record["symbol"]),
                exchange=str(record["exchange"]),
                market="A_SHARE",
                name=str(record["name"]),
                status=str(record["status"]),
                industry=None,
                listing_date=date(2001, 1, 1),
                delisting_date=None,
                source=self.code,
            )
            for record in raw_records
        ]


class MultiCapabilityProviderAdapter(SuccessOpenProviderAdapter):
    code = "multi_capability_provider"
    name = "Multi Capability Provider"

    def capabilities(self) -> AdapterCapability:
        return AdapterCapability(stock_list=True, daily_bars=True, calendars=True)

    def fetch_daily_bars(self, **kwargs):
        return [
            {"trade_date": date(2026, 6, 1), "close": 1675.0},
            {"trade_date": date(2026, 6, 2), "close": 1688.0},
        ]

    def normalize_daily_bars(self, raw_records):
        return [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=record["trade_date"],
                open=record["close"] - 10,
                high=record["close"] + 5,
                low=record["close"] - 15,
                close=record["close"],
                pre_close=None,
                volume=1000.0,
                amount=record["close"] * 1000,
                adjust_factor=1.0,
                source=self.code,
            )
            for record in raw_records
        ]

    def fetch_trading_calendar(self, **kwargs):
        return [{"trade_date": date(2026, 6, 1), "is_open": True}]

    def normalize_trading_calendar(self, raw_records, *, market: str):
        return [
            NormalizedTradingCalendar(
                market=market,
                trade_date=record["trade_date"],
                is_open=bool(record["is_open"]),
                source=self.code,
            )
            for record in raw_records
        ]


class InvalidDailyBarProviderAdapter(MultiCapabilityProviderAdapter):
    code = "invalid_daily_bar_provider"
    name = "Invalid Daily Bar Provider"

    def normalize_daily_bars(self, raw_records):
        return [
            NormalizedDailyBar(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                trade_date=record["trade_date"],
                open=record["close"],
                high=record["close"] - 1,
                low=record["close"],
                close=record["close"],
                pre_close=None,
                volume=1000.0,
                amount=record["close"] * 1000,
                adjust_factor=1.0,
                source=self.code,
            )
            for record in raw_records
        ]


class CurrentlyUnavailableProviderAdapter(SuccessOpenProviderAdapter):
    code = "currently_unavailable_provider"
    name = "Currently Unavailable Provider"

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(healthy=False, status="unavailable", message="package is not installed")


def test_data_sources_api_lists_known_open_provider_adapters(client, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    response = client.get("/api/data-sources")

    assert response.status_code == 200
    sources = response.json()
    source_codes = {source["code"] for source in sources}
    assert source_codes == {"akshare", "baostock", "stock_sdk"}

    akshare = next(source for source in sources if source["code"] == "akshare")
    assert akshare["enabled"] is True
    assert akshare["requires_token"] is False
    assert akshare["auth_status"] == "not_required"
    assert akshare["capabilities"]["stock_list"] is True
    assert akshare["provider_metadata"]["docs_url"] == "https://akshare.akfamily.xyz/data/stock/stock.html"
    assert akshare["adapter_class"] == "AkShareAdapter"
    assert akshare["config_json"]["capabilities"]["stock_list"] is True
    assert akshare["config_json"]["auth_status"] == "not_required"
    assert akshare["config_json"]["provider_metadata"]["docs_url"] == "https://akshare.akfamily.xyz/data/stock/stock.html"

    baostock = next(source for source in sources if source["code"] == "baostock")
    assert baostock["enabled"] is True
    assert baostock["requires_token"] is False
    assert baostock["auth_status"] == "not_required"
    assert baostock["config_json"]["auth_status"] == "not_required"
    assert baostock["config_json"]["provider_metadata"]["homepage_url"] == "http://baostock.com/"

    stock_sdk = next(source for source in sources if source["code"] == "stock_sdk")
    assert stock_sdk["enabled"] is False
    assert stock_sdk["requires_token"] is False
    assert stock_sdk["auth_status"] == "not_required"
    assert stock_sdk["config_json"]["capabilities"]["daily_bars"] is True
    assert stock_sdk["config_json"]["provider_metadata"]["homepage_url"] == "https://github.com/chengzuopeng/stock-sdk"


def test_data_source_catalog_lists_free_mcp_candidates_without_registering_them(client):
    response = client.get("/api/data-sources/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload == []  # MCP catalog was removed — no candidates

    list_response = client.get("/api/data-sources")
    assert list_response.status_code == 200

    list_response = client.get("/api/data-sources")
    assert list_response.status_code == 200
    registered_codes = {source["code"] for source in list_response.json()}
    assert "wind" not in registered_codes
    assert "choice" not in registered_codes


def test_data_source_update_preserves_user_priority(client):
    update_response = client.patch("/api/data-sources/baostock", json={"enabled": False, "priority": 7})
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["enabled"] is False
    assert updated["priority"] == 7

    list_response = client.get("/api/data-sources")
    assert list_response.status_code == 200
    baostock = next(source for source in list_response.json() if source["code"] == "baostock")
    assert baostock["enabled"] is False
    assert baostock["priority"] == 7


def test_registered_adapter_sync_promotes_legacy_akshare_defaults(client):
    db = SessionLocal()
    try:
        db.add(
            DataSource(
                code="akshare",
                name="AKShare",
                enabled=False,
                priority=60,
                requires_token=False,
                config_json={"adapter_class": "AkShareAdapter"},
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/data-sources")

    assert response.status_code == 200
    akshare = next(source for source in response.json() if source["code"] == "akshare")
    assert akshare["enabled"] is True
    assert akshare["priority"] == 10


def test_data_source_list_refreshes_stale_health_state(client):
    registry = AdapterRegistry()
    registry.register(CurrentlyUnavailableProviderAdapter())
    db = SessionLocal()
    try:
        stale_source = DataSource(
            code="currently_unavailable_provider",
            name="Currently Unavailable Provider",
            enabled=True,
            priority=10,
            requires_token=False,
            health_status="healthy",
            config_json={"last_health_message": "previous run was healthy"},
        )
        db.add(stale_source)
        db.commit()

        sources = DataSourceService(db, registry).list_sources()
        source = next(source for source in sources if source.code == "currently_unavailable_provider")
    finally:
        db.close()

    assert source.health_status == "unavailable"
    assert source.config_json["last_health_message"] == "package is not installed"


def test_data_sources_api_removes_non_v1_provider_rows(client):
    db = SessionLocal()
    try:
        db.add_all(
            [
                DataSource(
                    code="eastmoney",
                    name="EastMoney",
                    enabled=True,
                    priority=1,
                    requires_token=False,
                    config_json={"provider_metadata": {"provider_type": "legacy"}},
                ),
                DataSource(
                    code="mock_seed_provider",
                    name="Mock Seed Provider",
                    enabled=True,
                    priority=2,
                    requires_token=False,
                    config_json={"provider_metadata": {"provider_type": "test_fixture"}},
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/data-sources")

    assert response.status_code == 200
    source_codes = {source["code"] for source in response.json()}
    assert source_codes == {"akshare", "baostock", "stock_sdk"}

    db = SessionLocal()
    try:
        retired = {
            source.code: source
            for source in db.query(DataSource).filter(DataSource.code.in_(["eastmoney", "mock_seed_provider"])).all()
        }
    finally:
        db.close()

    assert set(retired) == {"eastmoney", "mock_seed_provider"}
    assert all(source.enabled is False for source in retired.values())
    assert all(source.health_status == "retired" for source in retired.values())
    assert all(source.config_json.get("retired") is True for source in retired.values())


def test_disabled_data_source_cannot_create_stock_sync(client):
    disable_response = client.patch("/api/data-sources/baostock", json={"enabled": False})
    assert disable_response.status_code == 200

    sync_response = client.post("/api/stocks/sync", json={"source": "baostock", "market": "A_SHARE"})

    assert sync_response.status_code == 400
    assert "disabled" in sync_response.json()["detail"]


def test_auto_stock_sync_candidates_skip_unavailable_enabled_sources(client):
    """Auto sync should only pick sources that are both enabled and available."""
    response = client.get("/api/data-sources")
    assert response.status_code == 200
    sources = response.json()
    for source in sources:
        if source["enabled"]:
            assert source["code"] in {"akshare", "baostock", "stock_sdk"}
