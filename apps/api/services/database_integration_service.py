from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.core.market_symbols import listed_common_stock_filter
from apps.api.models import Dataset, IngestBatch, Stock, SyncTask, TradingCalendar
from apps.api.repositories.daily_bars import DailyBarRepository
from apps.api.services.dataset_row_count_projection import sync_projected_dataset_row_count


DEFAULT_COVERAGE_MARKET = "A_SHARE"
DAILY_BAR_TARGET_WINDOW_DAYS = 180


class DatabaseIntegrationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.daily_bar_repo = DailyBarRepository()

    def get_overview(self, *, market: str | None = None) -> dict:
        coverage_market = _normalize_market(market)
        datasets = self._list_datasets()
        recent_batches = self._list_recent_batches(market=coverage_market)
        all_batches = self._list_batches_for_summary(market=coverage_market)

        dataset_snapshots = [
            _dataset_snapshot(dataset, row_count=sync_projected_dataset_row_count(self.db, dataset))
            for dataset in datasets
        ]
        self.db.commit()
        coverage_summary = self._coverage_summary(market=coverage_market)
        sync_watermarks = _build_sync_watermarks(all_batches, coverage_summary=coverage_summary)
        provider_integrations = _build_provider_integrations(all_batches)

        latest_data_date = _latest_date([dataset.latest_data_date for dataset in datasets])
        failed_batches_total = sum(1 for batch in all_batches if batch.status == "failed")
        fallback_successes_total = sum(1 for batch in all_batches if _is_fallback_success(batch))
        healthy_providers_total = sum(1 for provider in provider_integrations if provider["successes"] > 0)

        return {
            "summary": {
                "datasets_total": len(datasets),
                "total_rows": sum(snapshot["row_count"] or 0 for snapshot in dataset_snapshots),
                "latest_data_date": latest_data_date,
                "recent_batches_total": len(recent_batches),
                "failed_batches_total": failed_batches_total,
                "fallback_successes_total": fallback_successes_total,
                "healthy_providers_total": healthy_providers_total,
            },
            "coverage_summary": coverage_summary,
            "dataset_snapshots": dataset_snapshots,
            "sync_watermarks": sync_watermarks,
            "provider_integrations": provider_integrations,
            "recent_batches": [_recent_batch(batch) for batch in recent_batches],
        }

    def list_lineage(
        self,
        *,
        batch_id: int | None = None,
        dataset_name: str | None = None,
        market: str | None = None,
        symbol: str | None = None,
        trade_date: date | None = None,
        source: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        conditions = []
        normalized_dataset = _normalize_optional_text(dataset_name)
        normalized_market = _normalize_optional_market(market)
        normalized_symbol = _normalize_optional_text(symbol)
        normalized_source = _normalize_optional_text(source)
        normalized_status = _normalize_optional_text(status)

        if batch_id:
            conditions.append(IngestBatch.id == batch_id)
        if normalized_dataset:
            conditions.append(IngestBatch.dataset_name == normalized_dataset)
        if normalized_market:
            conditions.append(IngestBatch.market == normalized_market)
        if normalized_symbol:
            conditions.append(IngestBatch.symbol == normalized_symbol)
        if normalized_source:
            conditions.append(IngestBatch.source == normalized_source)
        if normalized_status:
            conditions.append(IngestBatch.status == normalized_status)
        if trade_date:
            conditions.extend(
                [
                    IngestBatch.start_date <= trade_date,
                    IngestBatch.end_date >= trade_date,
                ]
            )

        total_stmt = select(func.count(IngestBatch.id)).join(SyncTask, SyncTask.id == IngestBatch.task_id)
        records_stmt = (
            select(IngestBatch, SyncTask)
            .join(SyncTask, SyncTask.id == IngestBatch.task_id)
            .order_by(IngestBatch.started_at.desc(), IngestBatch.id.desc())
        )
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)

        total = self.db.scalar(total_stmt) or 0
        offset = (page - 1) * page_size
        rows = self.db.execute(records_stmt.offset(offset).limit(page_size)).all()
        items = [_lineage_item(batch=batch, task=task) for batch, task in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max((total + page_size - 1) // page_size, 1),
        }

    def _list_datasets(self) -> list[Dataset]:
        return list(self.db.scalars(select(Dataset).order_by(Dataset.layer.asc(), Dataset.name.asc())).all())

    def _list_recent_batches(self, *, market: str) -> list[IngestBatch]:
        return list(
            self.db.scalars(
                select(IngestBatch)
                .where(IngestBatch.market == market)
                .order_by(IngestBatch.started_at.desc(), IngestBatch.id.desc())
                .limit(8)
            ).all()
        )

    def _list_batches_for_summary(self, *, market: str) -> list[IngestBatch]:
        return list(
            self.db.scalars(
                select(IngestBatch)
                .where(IngestBatch.market == market)
                .order_by(IngestBatch.started_at.desc(), IngestBatch.id.desc())
                .limit(500)
            ).all()
        )

    def _coverage_summary(self, *, market: str) -> dict:
        stock_symbols = set(
            self.db.scalars(
                select(Stock.symbol).where(listed_common_stock_filter(market=market))
            ).all()
        )
        all_open_dates = set(
            self.db.scalars(
                select(TradingCalendar.trade_date).where(
                    TradingCalendar.market == market,
                    TradingCalendar.is_open.is_(True),
                )
            ).all()
        )
        calendar_latest_date = max(all_open_dates) if all_open_dates else None
        target_start_date = calendar_latest_date - timedelta(days=DAILY_BAR_TARGET_WINDOW_DAYS) if calendar_latest_date else None
        open_dates = {
            trade_date
            for trade_date in all_open_dates
            if target_start_date is None or trade_date >= target_start_date
        }
        coverage_status = "ok"
        coverage_message = None
        try:
            covered_pairs = {
                (symbol, trade_date)
                for symbol, trade_date in self.daily_bar_repo.market_symbol_trade_date_pairs(market=market)
                if symbol in stock_symbols and trade_date in open_dates
            }
        except Exception:
            covered_pairs = set()
            coverage_status = "degraded"
            coverage_message = "Parquet / DuckDB 覆盖率查询失败，当前日线完整度暂不可确认。"

        expected_symbol_days = len(stock_symbols) * len(open_dates)
        actual_symbol_days = len(covered_pairs)
        missing_symbol_days = 0 if coverage_status == "degraded" else max(expected_symbol_days - actual_symbol_days, 0)
        covered_stock_count = len({symbol for symbol, _ in covered_pairs})

        return {
            "market": market,
            "coverage_status": coverage_status,
            "coverage_message": coverage_message,
            "stock_pool_total": len(stock_symbols),
            "daily_covered_stock_count": covered_stock_count,
            "calendar_latest_date": calendar_latest_date,
            "coverage_start_date": target_start_date,
            "coverage_end_date": calendar_latest_date,
            "daily_expected_symbol_days": expected_symbol_days,
            "daily_actual_symbol_days": actual_symbol_days,
            "daily_missing_symbol_days": missing_symbol_days,
            "daily_completeness": None if coverage_status == "degraded" else _ratio(actual_symbol_days, expected_symbol_days),
        }


def _normalize_market(market: str | None) -> str:
    normalized = (market or "").strip().upper()
    return normalized or DEFAULT_COVERAGE_MARKET


def _normalize_optional_market(market: str | None) -> str | None:
    normalized = (market or "").strip().upper()
    return normalized or None


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _dataset_snapshot(dataset: Dataset, *, row_count: int) -> dict:
    return {
        "dataset_name": dataset.name,
        "layer": dataset.layer,
        "storage_type": dataset.storage_type,
        "source": dataset.source,
        "row_count": row_count,
        "latest_data_date": dataset.latest_data_date,
        "quality_status": dataset.quality_status,
        "dataset_version": _dataset_version(dataset),
        "schema_fields_count": len(dataset.schema_json or {}),
        "primary_keys_json": dataset.primary_keys_json or [],
        "partition_keys_json": dataset.partition_keys_json or [],
        "updated_at": dataset.updated_at,
    }


def _dataset_version(dataset: Dataset) -> str:
    updated = dataset.updated_at.strftime("%Y%m%d%H%M%S") if dataset.updated_at else "unknown"
    return f"{dataset.layer}-{updated}"


def _build_sync_watermarks(batches: list[IngestBatch], *, coverage_summary: dict) -> list[dict]:
    watermarks: dict[tuple[str, str, str | None, str | None], dict] = {}
    failures: dict[tuple[str, str, str | None, str | None], IngestBatch] = {}
    for batch in batches:
        key = (batch.dataset_name, batch.source, batch.market, batch.symbol)
        if batch.status == "failed":
            current_failure = failures.get(key)
            failed_at = batch.finished_at or batch.started_at
            if current_failure is None or _dt_value(failed_at) > _dt_value(
                current_failure.finished_at or current_failure.started_at
            ):
                failures[key] = batch
            continue
        if not _is_effective_success(batch):
            continue
        success_at = batch.finished_at or batch.started_at
        candidate = {
            "dataset_name": batch.dataset_name,
            "source": batch.source,
            "requested_source": batch.requested_source,
            "market": batch.market,
            "symbol": batch.symbol,
            "latest_success_date": _latest_date([batch.end_date, batch.start_date]),
            "last_success_at": success_at,
            "records_written": batch.records_written,
            "quality_status": batch.quality_status,
            "task_id": batch.task_id,
            "batch_id": batch.id,
            "last_failed_at": None,
            "last_failure_reason": None,
            "last_failure_task_id": None,
            "last_failure_batch_id": None,
            "repair_start_date": None,
            "repair_end_date": None,
            "repair_reason": None,
        }
        current = watermarks.get(key)
        if current is None or _dt_value(success_at) > _dt_value(current["last_success_at"]):
            watermarks[key] = candidate

    for key, watermark in watermarks.items():
        failure = failures.get(key)
        if failure is not None:
            watermark["last_failed_at"] = failure.finished_at or failure.started_at
            watermark["last_failure_reason"] = failure.error_message
            watermark["last_failure_task_id"] = failure.task_id
            watermark["last_failure_batch_id"] = failure.id
        _apply_repair_hint(watermark, coverage_summary=coverage_summary)

    for key, failure in failures.items():
        if key in watermarks:
            continue
        failed_at = failure.finished_at or failure.started_at
        repair_start = failure.start_date or coverage_summary.get("coverage_start_date")
        repair_end = failure.end_date or coverage_summary.get("coverage_end_date")
        watermarks[key] = {
            "dataset_name": failure.dataset_name,
            "source": failure.source,
            "requested_source": failure.requested_source,
            "market": failure.market,
            "symbol": failure.symbol,
            "latest_success_date": None,
            "last_success_at": None,
            "records_written": 0,
            "quality_status": "failed",
            "task_id": failure.task_id,
            "batch_id": failure.id,
            "last_failed_at": failed_at,
            "last_failure_reason": failure.error_message,
            "last_failure_task_id": failure.task_id,
            "last_failure_batch_id": failure.id,
            "repair_start_date": repair_start,
            "repair_end_date": repair_end,
            "repair_reason": "最近同步失败，建议按失败批次范围重新创建同步任务。",
        }

    return sorted(
        watermarks.values(),
        key=lambda item: (_dt_value(item["last_success_at"]) or _dt_value(item["last_failed_at"]), item["dataset_name"]),
        reverse=True,
    )[:12]


def _apply_repair_hint(watermark: dict, *, coverage_summary: dict) -> None:
    if watermark["dataset_name"] != "daily_bars":
        return

    latest_success_date = watermark["latest_success_date"]
    coverage_start = coverage_summary.get("coverage_start_date")
    coverage_end = coverage_summary.get("coverage_end_date")
    missing_days = coverage_summary.get("daily_missing_symbol_days") or 0
    stock_pool_total = coverage_summary.get("stock_pool_total") or 0
    covered_stock_count = coverage_summary.get("daily_covered_stock_count") or 0
    if not coverage_end or missing_days <= 0:
        return

    if stock_pool_total > covered_stock_count:
        watermark["repair_reason"] = (
            f"当前日线只覆盖 {covered_stock_count}/{stock_pool_total} 只股票，建议补齐该市场同区间日线。"
        )
        return
    else:
        repair_start = _next_day(latest_success_date) if latest_success_date else coverage_start
        watermark["repair_reason"] = "日线覆盖率未满，建议按该水位线补齐缺失交易日。"

    if repair_start and repair_start <= coverage_end:
        watermark["repair_start_date"] = repair_start
        watermark["repair_end_date"] = coverage_end


def _build_provider_integrations(batches: list[IngestBatch]) -> list[dict]:
    providers: dict[str, dict] = {}
    for batch in batches:
        provider = providers.setdefault(
            batch.source,
            {
                "source": batch.source,
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "fallback_successes": 0,
                "records_written": 0,
                "last_success_at": None,
                "last_failure_at": None,
            },
        )
        provider["attempts"] += 1
        if _is_effective_success(batch):
            success_at = batch.finished_at or batch.started_at
            provider["successes"] += 1
            provider["records_written"] += batch.records_written
            provider["last_success_at"] = _max_datetime(provider["last_success_at"], success_at)
            if _is_fallback_success(batch):
                provider["fallback_successes"] += 1
        if batch.status == "failed":
            provider["failures"] += 1
            provider["last_failure_at"] = _max_datetime(provider["last_failure_at"], batch.finished_at or batch.started_at)

    return sorted(
        providers.values(),
        key=lambda item: (_dt_value(item["last_success_at"]), item["successes"], item["records_written"]),
        reverse=True,
    )


def _recent_batch(batch: IngestBatch) -> dict:
    return {
        "id": batch.id,
        "task_id": batch.task_id,
        "dataset_name": batch.dataset_name,
        "source": batch.source,
        "requested_source": batch.requested_source,
        "market": batch.market,
        "symbol": batch.symbol,
        "start_date": batch.start_date,
        "end_date": batch.end_date,
        "status": batch.status,
        "schema_version": batch.schema_version,
        "normalize_version": batch.normalize_version,
        "records_written": batch.records_written,
        "quality_status": batch.quality_status,
        "error_message": batch.error_message,
        "started_at": batch.started_at,
        "finished_at": batch.finished_at,
    }


def _lineage_item(*, batch: IngestBatch, task: SyncTask) -> dict:
    return {
        "id": batch.id,
        "task_id": batch.task_id,
        "task_type": task.task_type,
        "task_status": task.status,
        "task_source": task.source,
        "task_error_message": task.error_message,
        "dataset_name": batch.dataset_name,
        "source": batch.source,
        "requested_source": batch.requested_source,
        "market": batch.market,
        "symbol": batch.symbol,
        "start_date": batch.start_date,
        "end_date": batch.end_date,
        "status": batch.status,
        "schema_version": batch.schema_version,
        "normalize_version": batch.normalize_version,
        "raw_records": batch.raw_records,
        "normalized_records": batch.normalized_records,
        "records_written": batch.records_written,
        "validation_errors_json": batch.validation_errors_json,
        "error_message": batch.error_message,
        "quality_status": batch.quality_status,
        "started_at": batch.started_at,
        "finished_at": batch.finished_at,
        "created_at": batch.created_at,
    }


def _is_fallback_success(batch: IngestBatch) -> bool:
    return _is_effective_success(batch) and batch.requested_source == "auto" and batch.source != "auto"


def _is_effective_success(batch: IngestBatch) -> bool:
    return batch.status == "success" and batch.records_written > 0


def _latest_date(values: list[date | None]) -> date | None:
    dates = [value for value in values if value is not None]
    return max(dates) if dates else None


def _ratio(actual: int, expected: int) -> float | None:
    if expected <= 0:
        return None
    return min(1.0, round(actual / expected, 4))


def _max_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _dt_value(value: datetime | None) -> float:
    return value.timestamp() if value else 0


def _next_day(value: date | None) -> date | None:
    return value + timedelta(days=1) if value else None
