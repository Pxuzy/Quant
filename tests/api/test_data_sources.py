from __future__ import annotations

from datetime import date

from apps.api.adapters.base import (
    AdapterCapability,
    HealthCheckResult,
    NormalizedDailyBar,
    NormalizedStock,
    NormalizedTradingCalendar,
    ProviderMetadata,
    StockDataSourceAdapter,
)
from apps.api.adapters.registry import AdapterRegistry
from apps.api.db.session import SessionLocal
from apps.api.models import DataSource, Dataset, IngestBatch, Stock, SyncTask
from apps.api.services.data_source_service import DataSourceService
from apps.api.services.stock_sync_service import StockSyncService


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
    assert source_codes == {"akshare", "baostock", "adata", "tushare", "stock_sdk"}

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

    adata = next(source for source in sources if source["code"] == "adata")
    assert adata["enabled"] is True
    assert adata["requires_token"] is False
    assert adata["auth_status"] == "not_required"
    assert adata["config_json"]["capabilities"]["daily_bars"] is True
    assert adata["config_json"]["provider_metadata"]["homepage_url"] == "https://github.com/1nchaos/adata"

    tushare = next(source for source in sources if source["code"] == "tushare")
    assert tushare["enabled"] is False
    assert tushare["requires_token"] is True
    assert tushare["auth_status"] == "missing"
    assert tushare["capabilities"]["stock_list"] is True
    assert tushare["capabilities"]["daily_bars"] is True
    assert tushare["capabilities"]["calendars"] is True
    assert tushare["provider_metadata"]["auth_mode"] == "token"
    assert tushare["adapter_class"] == "TushareAdapter"
    assert tushare["config_json"]["auth_status"] == "missing"
    assert tushare["config_json"]["provider_metadata"]["auth_mode"] == "token"

    stock_sdk = next(source for source in sources if source["code"] == "stock_sdk")
    assert stock_sdk["enabled"] is False
    assert stock_sdk["requires_token"] is False
    assert stock_sdk["auth_status"] == "not_required"
    assert stock_sdk["config_json"]["capabilities"]["daily_bars"] is True
    assert stock_sdk["config_json"]["provider_metadata"]["homepage_url"] == "https://github.com/chengzuopeng/stock-sdk"


def test_tushare_auth_status_reports_configured_when_token_exists(client, monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "test-token")

    response = client.get("/api/data-sources")

    assert response.status_code == 200
    tushare = next(source for source in response.json() if source["code"] == "tushare")
    assert tushare["auth_status"] == "configured"
    assert tushare["config_json"]["auth_status"] == "configured"


def test_tushare_metadata_declares_mcp_and_sector_capabilities(client, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    response = client.get("/api/data-sources")

    assert response.status_code == 200
    tushare = next(source for source in response.json() if source["code"] == "tushare")
    metadata = tushare["provider_metadata"]
    assert metadata["docs_url"] == "https://tushare.pro/document/1?doc_id=108"
    assert metadata["mcp_url"] == "https://tushare.pro/document/1?doc_id=463"
    assert metadata["mcp_role"] == "adapter_layer"
    assert "index_classify" in metadata["sector_capabilities"]
    assert "index_member_all" in metadata["sector_capabilities"]
    assert "industry and sector datasets" in metadata["rate_limit_note"]


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
    assert "tushare_mcp" not in registered_codes
    assert "tushare" in registered_codes


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
    assert source_codes == {"akshare", "baostock", "adata", "tushare", "stock_sdk"}


def test_disabled_data_source_cannot_create_stock_sync(client):
    disable_response = client.patch("/api/data-sources/baostock", json={"enabled": False})
    assert disable_response.status_code == 200

    sync_response = client.post("/api/stocks/sync", json={"source": "baostock", "market": "A_SHARE"})

    assert sync_response.status_code == 400
    assert "disabled" in sync_response.json()["detail"]


def test_auto_stock_sync_candidates_skip_unavailable_enabled_sources(client):
    registry = AdapterRegistry()
    registry.register(CurrentlyUnavailableProviderAdapter())
    registry.register(SuccessOpenProviderAdapter())
    db = SessionLocal()
    try:
        service = StockSyncService(db, registry)
        task = service.create_stock_sync_task(source="auto", market="A_SHARE")
        candidate_sources = task.logs[0].payload_json["candidate_sources"]
    finally:
        db.close()

    assert candidate_sources == ["success_open_provider"]


def test_known_optional_provider_health_check_reports_status(client):
    response = client.post("/api/data-sources/tushare/health-check")

    assert response.status_code == 200
    payload = response.json()
    assert payload["healthy"] in {True, False}
    assert payload["status"] in {"healthy", "unavailable", "unhealthy"}
    assert payload["source"]["health_status"] == payload["status"]
    assert payload["source"]["config_json"]["last_health_message"]


def test_data_source_smoke_test_success_records_sample_and_health_without_sync_side_effects(client):
    registry = AdapterRegistry()
    registry.register(SuccessOpenProviderAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("success_open_provider")
        source = service.data_source_repo.get_by_code("success_open_provider")
        stock_count = db.query(Stock).count()
        dataset_count = db.query(Dataset).count()
        task_count = db.query(SyncTask).count()
    finally:
        db.close()

    assert payload["healthy"] is True
    assert payload["status"] == "healthy"
    assert payload["capability"] == "stock_list"
    assert payload["raw_records"] == 2
    assert payload["normalized_records"] == 2
    assert payload["sample"][0]["symbol"] == "600519"
    assert payload["sample"][0]["source"] == "success_open_provider"
    assert source is not None
    assert source.health_status == "healthy"
    assert source.config_json["last_smoke_test"]["capability"] == "stock_list"
    assert source.config_json["last_smoke_test"]["status"] == "healthy"
    assert source.config_json["last_smoke_test"]["raw_records"] == 2
    assert source.config_json["last_smoke_test"]["normalized_records"] == 2
    assert source.config_json["last_smoke_test"]["sample"][0]["symbol"] == "600519"
    assert source.config_json["smoke_test_history"][0]["message"] == payload["message"]
    assert source.config_json["last_health_message"] == payload["message"]
    assert stock_count == 0
    assert dataset_count == 0
    assert task_count == 0


def test_data_source_smoke_test_releases_metadata_write_before_provider_fetch(client):
    registry = AdapterRegistry()
    registry.register(WriteDuringFetchProviderAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("write_during_fetch_provider")
        probe = service.data_source_repo.get_by_code("write_during_fetch_probe")
    finally:
        db.close()

    assert payload["healthy"] is True
    assert probe is not None


def test_data_source_smoke_test_can_target_daily_bars_capability(client):
    registry = AdapterRegistry()
    registry.register(MultiCapabilityProviderAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("multi_capability_provider", capability="daily_bars")
        source = service.data_source_repo.get_by_code("multi_capability_provider")
    finally:
        db.close()

    assert payload["healthy"] is True
    assert payload["capability"] == "daily_bars"
    assert payload["raw_records"] == 2
    assert payload["normalized_records"] == 2
    assert payload["sample"][0]["symbol"] == "600519"
    assert payload["sample"][0]["trade_date"] == "2026-06-01"
    assert payload["sample"][0]["close"] == 1675.0
    assert source is not None
    assert source.config_json["last_smoke_test"]["capability"] == "daily_bars"
    assert source.config_json["last_smoke_test"]["validation_errors"] == []


def test_data_source_smoke_test_uses_formal_schema_validation(client):
    registry = AdapterRegistry()
    registry.register(InvalidDailyBarProviderAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("invalid_daily_bar_provider", capability="daily_bars")
        source = service.data_source_repo.get_by_code("invalid_daily_bar_provider")
    finally:
        db.close()

    assert payload["healthy"] is False
    assert payload["status"] == "unhealthy"
    assert payload["raw_records"] == 2
    assert payload["normalized_records"] == 2
    assert any("high" in error for error in payload["validation_errors"])
    assert source is not None
    assert source.config_json["last_smoke_test"]["validation_errors"] == payload["validation_errors"]


def test_data_source_smoke_test_rejects_unsupported_capability(client):
    registry = AdapterRegistry()
    registry.register(SuccessOpenProviderAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("success_open_provider", capability="daily_bars")
        source = service.data_source_repo.get_by_code("success_open_provider")
    finally:
        db.close()

    assert payload["healthy"] is False
    assert payload["status"] == "unhealthy"
    assert payload["capability"] == "daily_bars"
    assert "不支持" in payload["message"]
    assert source is not None
    assert source.config_json["last_smoke_test"]["status"] == "unhealthy"


def test_data_source_smoke_test_api_accepts_capability_query(client):
    response = client.post("/api/data-sources/baostock/smoke-test?capability=calendars")

    assert response.status_code == 200
    payload = response.json()
    assert payload["capability"] == "calendars"


def test_data_source_smoke_test_failure_marks_source_unhealthy(client):
    registry = AdapterRegistry()
    registry.register(FailingFetchAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("failing_fetch")
        source = service.data_source_repo.get_by_code("failing_fetch")
    finally:
        db.close()

    assert payload["healthy"] is False
    assert payload["status"] == "unhealthy"
    assert payload["capability"] == "stock_list"
    assert payload["raw_records"] == 0
    assert payload["normalized_records"] == 0
    assert payload["sample"] == []
    assert source is not None
    assert source.health_status == "unhealthy"
    assert source.config_json["last_health_message"] == "fetch failed"
    assert source.config_json["last_smoke_test"]["status"] == "unhealthy"
    assert source.config_json["smoke_test_history"][0]["message"] == "fetch failed"


def test_data_source_smoke_test_failure_message_is_sanitized_for_ui(client):
    registry = AdapterRegistry()
    registry.register(LeakyFetchAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("leaky_fetch")
        source = service.data_source_repo.get_by_code("leaky_fetch")
    finally:
        db.close()

    assert payload["status"] == "unhealthy"
    assert "secret.example.test" not in payload["message"]
    assert "hidden.example.test" not in payload["message"]
    assert "https://" not in payload["message"]
    assert len(payload["message"]) <= 240
    assert source is not None
    assert source.config_json["last_health_message"] == payload["message"]
    assert source.config_json["smoke_test_history"][0]["message"] == payload["message"]


def test_data_source_smoke_test_marks_upstream_network_error_unavailable(client):
    registry = AdapterRegistry()
    registry.register(NetworkUnavailableAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("network_unavailable", capability="daily_bars")
        source = service.data_source_repo.get_by_code("network_unavailable")
    finally:
        db.close()

    assert payload["healthy"] is False
    assert payload["status"] == "unavailable"
    assert payload["capability"] == "daily_bars"
    assert payload["raw_records"] == 0
    assert payload["normalized_records"] == 0
    assert "NETWORK_ERROR" in payload["message"]
    assert "https://" not in payload["message"]
    assert source is not None
    assert source.health_status == "unavailable"
    assert source.config_json["last_smoke_test"]["status"] == "unavailable"


def test_data_source_smoke_test_keeps_recent_history(client):
    registry = AdapterRegistry()
    registry.register(SuccessOpenProviderAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        for _ in range(6):
            service.smoke_test_source("success_open_provider")
        source = service.data_source_repo.get_by_code("success_open_provider")
    finally:
        db.close()

    assert source is not None
    history = source.config_json["smoke_test_history"]
    assert len(history) == 5
    assert all(item["status"] == "healthy" for item in history)
    assert all(item["sample"][0]["symbol"] == "600519" for item in history)


def test_data_source_smoke_test_empty_normalized_records_is_unhealthy(client):
    registry = AdapterRegistry()
    registry.register(EmptyNormalizeAdapter())
    db = SessionLocal()
    try:
        service = DataSourceService(db, registry)
        payload = service.smoke_test_source("empty_normalize")
        source = service.data_source_repo.get_by_code("empty_normalize")
    finally:
        db.close()

    assert payload["healthy"] is False
    assert payload["status"] == "unhealthy"
    assert payload["raw_records"] == 1
    assert payload["normalized_records"] == 0
    assert source is not None
    assert source.config_json["last_smoke_test"]["raw_records"] == 1
    assert source.config_json["last_smoke_test"]["normalized_records"] == 0
    assert source.config_json["smoke_test_history"][0]["status"] == "unhealthy"
    assert "returned no normalized stock_list records" in source.config_json["last_health_message"]


def test_data_source_smoke_test_unknown_code_returns_404(client):
    response = client.post("/api/data-sources/not-a-provider/smoke-test")

    assert response.status_code == 404
    assert "Unknown data source" in response.json()["detail"]


def test_stock_sync_failure_marks_source_unhealthy(client):
    registry = AdapterRegistry()
    registry.register(FailingFetchAdapter())
    db = SessionLocal()
    try:
        service = StockSyncService(db, registry)
        task = service.run_stock_sync(source="failing_fetch", market="A_SHARE")
        failing_source = service.data_source_repo.get_by_code("failing_fetch")
    finally:
        db.close()

    assert failing_source is not None
    assert task.status == "failed"
    assert task.error_message == "fetch failed"
    assert failing_source.health_status == "unhealthy"
    assert failing_source.config_json["last_health_message"] == "fetch failed"


def test_auto_stock_sync_falls_back_to_next_enabled_source(client):
    registry = AdapterRegistry()
    registry.register(FailingFetchAdapter())
    registry.register(SuccessOpenProviderAdapter())
    db = SessionLocal()
    try:
        service = StockSyncService(db, registry)
        task = service.run_stock_sync(source="auto", market="A_SHARE")
        logs = [log for log in task.logs]
        dataset = db.query(Dataset).filter(Dataset.name == "stocks").one()
    finally:
        db.close()

    assert task.status == "success"
    assert task.source == "auto"
    assert task.records_written == 2
    assert dataset.source == "success_open_provider"
    assert any(log.message == "Provider attempt failed." and log.payload_json["source"] == "failing_fetch" for log in logs)
    assert any(
        log.message == "Stock list sync completed." and log.payload_json["selected_source"] == "success_open_provider"
        for log in logs
    )


def test_stock_sync_keeps_only_listed_common_a_share_stock_pool(client):
    registry = AdapterRegistry()
    registry.register(MixedSecurityProviderAdapter())
    db = SessionLocal()
    try:
        service = StockSyncService(db, registry)
        task = service.run_stock_sync(source="mixed_security_provider", market="A_SHARE")
        stocks = db.query(Stock).order_by(Stock.exchange, Stock.symbol).all()
        dataset = db.query(Dataset).filter(Dataset.name == "stocks").one()
        batch = db.query(IngestBatch).filter(IngestBatch.task_id == task.id).one()
    finally:
        db.close()

    identities = {(stock.symbol, stock.exchange) for stock in stocks}
    assert task.status == "success"
    assert task.records_read == 7
    assert task.records_written == 3
    assert batch.raw_records == 7
    assert batch.normalized_records == 3
    assert batch.records_written == 3
    assert dataset.row_count == 3
    assert identities == {("600519", "SSE"), ("000001", "SZSE"), ("430047", "BSE")}


def test_auto_stock_sync_skips_disabled_sources(client):
    registry = AdapterRegistry()
    registry.register(FailingFetchAdapter())
    registry.register(SuccessOpenProviderAdapter())
    db = SessionLocal()
    try:
        service = StockSyncService(db, registry)
        service.data_source_repo.sync_registered_adapters(registry)
        service.data_source_repo.update_source("failing_fetch", enabled=False)
        db.commit()

        task = service.run_stock_sync(source="auto", market="A_SHARE")
        logs = [log for log in task.logs]
    finally:
        db.close()

    assert task.status == "success"
    assert not any(
        log.message == "Provider attempt started." and log.payload_json["source"] == "failing_fetch" for log in logs
    )
