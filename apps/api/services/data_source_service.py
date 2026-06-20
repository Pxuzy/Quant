from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.adapters.base import HealthCheckResult, NormalizedDailyBar, NormalizedStock, NormalizedTradingCalendar
from apps.api.adapters.registry import AdapterRegistry, default_adapter_registry
from apps.api.models import DataSource
from apps.api.repositories.data_sources import DataSourceRepository
from apps.api.services.normalized_data_validation import (
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

    def update_source(self, code: str, *, enabled: bool | None = None, priority: int | None = None) -> DataSource | None:
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
        if selected_capability is not None and selected_capability not in SMOKE_CAPABILITIES:
            raise ValueError(f"Unsupported smoke capability '{selected_capability}'.")
        if selected_capability is None:
            result = HealthCheckResult(
                healthy=False,
                status="unhealthy",
                message=f"Data source '{code}' does not declare a smoke-testable capability.",
            )
            self.data_source_repo.update_health(code, result)
            self._store_smoke_result(
                source=source,
                result=result,
                capability="none",
                raw_records=[],
                normalized_records=[],
                validation_errors=[],
            )
            self.db.commit()
            self.db.refresh(source)
            return self._smoke_payload(
                source=source,
                result=result,
                capability="none",
                raw_records=[],
                normalized_records=[],
                validation_errors=[],
            )
        elif not capabilities.get(selected_capability):
            result = HealthCheckResult(
                healthy=False,
                status="unhealthy",
                message=f"{adapter.name} 不支持 {selected_capability} 真实取样。",
            )
            self.data_source_repo.update_health(code, result)
            self._store_smoke_result(
                source=source,
                result=result,
                capability=selected_capability,
                raw_records=[],
                normalized_records=[],
                validation_errors=[],
            )
            self.db.commit()
            self.db.refresh(source)
            return self._smoke_payload(
                source=source,
                result=result,
                capability=selected_capability,
                raw_records=[],
                normalized_records=[],
                validation_errors=[],
            )

        try:
            raw_records, normalized_records = self._run_smoke(adapter=adapter, capability=selected_capability)
            validation_errors = _validate_smoke_records(
                capability=selected_capability,
                source=adapter.code,
                records=normalized_records,
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
            result = HealthCheckResult(
                healthy=healthy,
                status="healthy" if healthy else "unhealthy",
                message=message,
            )
        except ModuleNotFoundError as exc:
            raw_records = []
            normalized_records = []
            validation_errors = []
            result = HealthCheckResult(healthy=False, status="unavailable", message=str(exc))
        except RuntimeError as exc:
            raw_records = []
            normalized_records = []
            validation_errors = []
            raw_message = str(exc)
            message = _safe_smoke_error_message(raw_message)
            status = "unavailable" if _is_unavailable_smoke_error(raw_message) else "unhealthy"
            result = HealthCheckResult(healthy=False, status=status, message=message)
        except Exception as exc:
            raw_records = []
            normalized_records = []
            validation_errors = []
            result = HealthCheckResult(healthy=False, status="unhealthy", message=_safe_smoke_error_message(str(exc)))

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
            raw_records = adapter.fetch_stock_list(market="A_SHARE")
            normalized_records = adapter.normalize_stock_list(raw_records)
            return raw_records, normalized_records
        if capability == "calendars":
            raw_records = adapter.fetch_trading_calendar(market="A_SHARE", start_date=start_date, end_date=today)
            normalized_records = adapter.normalize_trading_calendar(raw_records, market="A_SHARE")
            return raw_records, normalized_records
        if capability == "daily_bars":
            raw_records = adapter.fetch_daily_bars(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                start_date=start_date,
                end_date=today,
            )
            normalized_records = adapter.normalize_daily_bars(raw_records)
            return raw_records, normalized_records
        raise ValueError(f"Unsupported smoke capability '{capability}'.")

    @staticmethod
    def _preferred_smoke_capability(capabilities: dict[str, bool]) -> str | None:
        for capability in SMOKE_CAPABILITIES:
            if capabilities.get(capability):
                return capability
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
            "sample": [_normalized_record_to_dict(record) for record in normalized_records[:3]],
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
            "sample": [_normalized_record_to_dict(record) for record in normalized_records[:3]],
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
    *,
    adapter_name: str,
    capability: str,
    normalized_count: int,
    validation_errors: list[str],
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
