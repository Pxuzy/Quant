from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.adapters.base import HealthCheckResult, NormalizedDailyBar, NormalizedStock, NormalizedTradingCalendar
from backend.app.adapters.registry import AdapterRegistry, default_adapter_registry
from backend.app.models import DataSource
from backend.app.repositories.data_sources import DataSourceRepository
from backend.app.services.normalized_data_validation import (
    validate_calendar_records,
    validate_daily_bar_records,
    validate_stock_records,
)

MAX_SMOKE_ERROR_MESSAGE_LENGTH = 240
SMOKE_HISTORY_LIMIT = 5
SMOKE_CAPABILITIES = ("stock_list", "daily_bars", "calendars")
URL_PATTERN = re.compile(r"https?://\S+")
HOST_PATTERN = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
REQUEST_DETAIL_PATTERN = re.compile(r"(?:with url:|url:)\s+\S+")


class DataSourceService:
    def __init__(self, db: Session, registry: AdapterRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or default_adapter_registry()
        self.data_source_repo = DataSourceRepository(db)

    def list_sources(self) -> list[DataSource]:
        self.data_source_repo.sync_registered_adapters(self.registry)
        for adapter in self.registry.list():
            self.data_source_repo.update_health(adapter.code, adapter.health_check())
        self.db.commit()
        return self.data_source_repo.list_all()

    def list_catalog(self) -> list[dict]:
        return DATA_SOURCE_CATALOG

    def record_sync_result(self, code: str, *, success: bool, capability: str) -> None:
        """记录一次 auto 同步的结果，用于动态排序。"""
        source = self.data_source_repo.get_by_code(code)
        if source is None:
            return
        config = source.config_json if isinstance(source.config_json, dict) else {}
        stats = config.get("usage_stats", {})
        cap_stats = stats.get(capability, {"total": 0, "success": 0})
        cap_stats["total"] = cap_stats.get("total", 0) + 1
        if success:
            cap_stats["success"] = cap_stats.get("success", 0) + 1
            cap_stats["last_success"] = datetime.now(timezone.utc).isoformat()
        else:
            cap_stats["last_failure"] = datetime.now(timezone.utc).isoformat()
        stats[capability] = cap_stats
        source.config_json = {**config, "usage_stats": stats}
        self.db.flush()

    def score_adapters(self, candidates: list, capability: str) -> list:
        """按历史成功率对候选适配器排序（成功率高优先），无历史数据按静态 priority 排。"""
        scored = []
        for adapter in candidates:
            source = self.data_source_repo.get_by_code(adapter.code)
            if source is not None:
                config = source.config_json if isinstance(source.config_json, dict) else {}
                cap_stats = config.get("usage_stats", {}).get(capability, {})
                total = cap_stats.get("total", 0) or 0
                success = cap_stats.get("success", 0) or 0
                if total > 0:
                    rate = success / total
                else:
                    rate = -1  # 无历史数据，按 priority 排
            else:
                rate = -1
            scored.append((rate, adapter.priority, adapter))
        # 降序：成功率高的先尝试；相同成功率下 priority 小的优先
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [item[2] for item in scored]

    def update_source(
        self, code: str, *, enabled: bool | None = None, priority: int | None = None
    ) -> DataSource | None:
        self.data_source_repo.sync_registered_adapters(self.registry)
        data_source = self.data_source_repo.update_source(code, enabled=enabled, priority=priority)
        if data_source is None:
            self.db.rollback()
            return None
        self.db.commit()
        self.db.refresh(data_source)
        return data_source

    def check_source_health(self, code: str) -> dict:
        adapter = self.registry.get(code)
        source = self.data_source_repo.upsert_adapter(adapter)
        result = adapter.health_check()
        self.data_source_repo.update_health(code, result)
        self.db.commit()
        self.db.refresh(source)
        return {
            "source": source,
            "healthy": result.healthy,
            "status": result.status,
            "message": result.message,
        }

    def smoke_test_source(self, code: str, *, capability: str | None = None) -> dict:
        adapter = self.registry.get(code)
        source = self.data_source_repo.upsert_adapter(adapter)
        capabilities = adapter.capabilities().to_dict()
        selected_capability = capability.strip() if capability else self._preferred_smoke_capability(capabilities)
        self.db.commit()

        def _fail(result: HealthCheckResult, cap: str) -> dict:
            self.data_source_repo.update_health(code, result)
            payload = self._smoke_payload(
                source=source,
                result=result,
                capability=cap,
                raw_records=[],
                normalized_records=[],
                validation_errors=[],
            )
            self._store_smoke_result(
                source=source,
                result=result,
                capability=cap,
                raw_records=[],
                normalized_records=[],
                validation_errors=[],
            )
            self.db.commit()
            self.db.refresh(source)
            return payload

        if selected_capability is not None and selected_capability not in SMOKE_CAPABILITIES:
            raise ValueError(f"Unsupported smoke capability '{selected_capability}'.")
        if selected_capability is None:
            return _fail(
                HealthCheckResult(
                    healthy=False,
                    status="unhealthy",
                    message=f"Data source '{code}' does not declare a smoke-testable capability.",
                ),
                "none",
            )
        if not capabilities.get(selected_capability):
            return _fail(
                HealthCheckResult(
                    healthy=False, status="unhealthy", message=f"{adapter.name} 不支持 {selected_capability} 真实取样。"
                ),
                selected_capability,
            )

        try:
            raw_records, normalized_records = self._run_smoke(adapter=adapter, capability=selected_capability)
            validation_errors = _validate_smoke_records(
                capability=selected_capability, source=adapter.code, records=normalized_records
            )
            healthy = bool(normalized_records) and not validation_errors
            message = (
                f"{adapter.name} smoke test succeeded with {len(normalized_records)} normalized {selected_capability} records."
                if healthy
                else _smoke_failure_message(
                    adapter_name=adapter.name,
                    capability=selected_capability,
                    normalized_count=len(normalized_records),
                    validation_errors=validation_errors,
                )
            )
            result = HealthCheckResult(healthy=healthy, status="healthy" if healthy else "unhealthy", message=message)
        except ModuleNotFoundError as exc:
            result = HealthCheckResult(healthy=False, status="unavailable", message=str(exc))
            raw_records, normalized_records, validation_errors = [], [], []
        except RuntimeError as exc:
            raw_message = str(exc)
            message = _safe_smoke_error_message(raw_message)
            status = "unavailable" if _is_unavailable_smoke_error(raw_message) else "unhealthy"
            result = HealthCheckResult(healthy=False, status=status, message=message)
            raw_records, normalized_records, validation_errors = [], [], []
        except Exception as exc:
            raw_message = str(exc)
            status = "unavailable" if _is_unavailable_smoke_error(raw_message) else "unhealthy"
            result = HealthCheckResult(healthy=False, status=status, message=_safe_smoke_error_message(raw_message))
            raw_records, normalized_records, validation_errors = [], [], []

        self.data_source_repo.update_health(code, result)
        self._store_smoke_result(
            source=source,
            result=result,
            capability=selected_capability,
            raw_records=raw_records,
            normalized_records=normalized_records,
            validation_errors=validation_errors,
        )
        self.db.commit()
        self.db.refresh(source)
        return self._smoke_payload(
            source=source,
            result=result,
            capability=selected_capability,
            raw_records=raw_records,
            normalized_records=normalized_records,
            validation_errors=validation_errors,
        )

    def _run_smoke(self, *, adapter, capability: str) -> tuple[list[dict], list]:
        today = date.today()
        start_date = today - timedelta(days=14)
        if capability == "stock_list":
            raw = adapter.fetch_stock_list(market="A_SHARE")
            return raw, adapter.normalize_stock_list(raw)
        if capability == "calendars":
            raw = adapter.fetch_trading_calendar(market="A_SHARE", start_date=start_date, end_date=today)
            return raw, adapter.normalize_trading_calendar(raw, market="A_SHARE")
        if capability == "daily_bars":
            raw = adapter.fetch_daily_bars(
                symbol="600519", exchange="SSE", market="A_SHARE", start_date=start_date, end_date=today
            )
            return raw, adapter.normalize_daily_bars(raw)
        raise ValueError(f"Unsupported smoke capability '{capability}'.")

    @staticmethod
    def _preferred_smoke_capability(capabilities: dict[str, bool]) -> str | None:
        for cap in SMOKE_CAPABILITIES:
            if capabilities.get(cap):
                return cap
        return None

    def _store_smoke_result(
        self,
        *,
        source: DataSource,
        result: HealthCheckResult,
        capability: str,
        raw_records: list[dict],
        normalized_records: list,
        validation_errors: list[str] | None = None,
    ) -> None:
        config_json = source.config_json if isinstance(source.config_json, dict) else {}
        smoke_record = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "healthy": result.healthy,
            "status": result.status,
            "message": result.message,
            "capability": capability,
            "raw_records": len(raw_records),
            "normalized_records": len(normalized_records),
            "validation_errors": validation_errors or [],
            "sample": [_normalized_record_to_dict(r) for r in normalized_records[:3]],
        }
        existing_history = config_json.get("smoke_test_history")
        smoke_history = existing_history if isinstance(existing_history, list) else []
        source.config_json = {
            **config_json,
            "last_smoke_test": smoke_record,
            "smoke_test_history": [smoke_record, *smoke_history][:SMOKE_HISTORY_LIMIT],
        }
        self.db.flush()

    @staticmethod
    def _smoke_payload(
        *,
        source: DataSource,
        result: HealthCheckResult,
        capability: str,
        raw_records: list[dict],
        normalized_records: list,
        validation_errors: list[str] | None = None,
    ) -> dict:
        return {
            "source": source,
            "healthy": result.healthy,
            "status": result.status,
            "message": result.message,
            "capability": capability,
            "raw_records": len(raw_records),
            "normalized_records": len(normalized_records),
            "validation_errors": validation_errors or [],
            "sample": [_normalized_record_to_dict(r) for r in normalized_records[:3]],
        }


def _normalized_record_to_dict(record) -> dict:
    if isinstance(record, NormalizedStock):
        return {
            "symbol": record.symbol,
            "exchange": record.exchange,
            "market": record.market,
            "name": record.name,
            "source": record.source,
        }
    if isinstance(record, NormalizedTradingCalendar):
        return {
            "market": record.market,
            "trade_date": record.trade_date.isoformat(),
            "is_open": record.is_open,
            "source": record.source,
        }
    if isinstance(record, NormalizedDailyBar):
        return {
            "symbol": record.symbol,
            "exchange": record.exchange,
            "market": record.market,
            "trade_date": record.trade_date.isoformat(),
            "open": record.open,
            "high": record.high,
            "low": record.low,
            "close": record.close,
            "volume": record.volume,
            "amount": record.amount,
            "source": record.source,
        }
    return dict(record) if isinstance(record, dict) else {"value": str(record)}


def _validate_smoke_records(*, capability: str, source: str, records: list) -> list[str]:
    if capability == "stock_list":
        return validate_stock_records(records, source=source, market="A_SHARE")
    if capability == "daily_bars":
        return validate_daily_bar_records(records, source=source, market="A_SHARE")
    if capability == "calendars":
        return validate_calendar_records(records, source=source, market="A_SHARE")
    return []


def _smoke_failure_message(
    *, adapter_name: str, capability: str, normalized_count: int, validation_errors: list[str]
) -> str:
    if normalized_count <= 0:
        return f"{adapter_name} smoke test returned no normalized {capability} records."
    first_error = validation_errors[0] if validation_errors else "unknown schema validation error"
    return f"{adapter_name} smoke test schema validation failed: {first_error}"


def _is_unavailable_smoke_error(message: str) -> bool:
    normalized = message.lower()
    return any(
        marker in normalized
        for marker in (
            "not configured",
            "not installed",
            "network error",
            "network_error",
            "remote end closed connection",
            "connection aborted",
            "timed out",
            "timeout",
        )
    )


def _safe_smoke_error_message(message: str) -> str:
    cleaned = URL_PATTERN.sub("[upstream URL]", message.strip())
    cleaned = REQUEST_DETAIL_PATTERN.sub("with upstream request details", cleaned)
    cleaned = re.sub(r"host='[^']+'", "host='[upstream host]'", cleaned)
    cleaned = HOST_PATTERN.sub("[upstream host]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > MAX_SMOKE_ERROR_MESSAGE_LENGTH:
        return f"{cleaned[: MAX_SMOKE_ERROR_MESSAGE_LENGTH - 3].rstrip()}..."
    return cleaned


DATA_SOURCE_CATALOG: list[dict] = []
