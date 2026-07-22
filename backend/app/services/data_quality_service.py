from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from math import ceil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import DataQualityReport, Dataset, IngestBatch, Stock, TradingCalendar
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.services.dataset_service import project_dataset_row_count, sync_projected_dataset_row_count

DAILY_BAR_REQUIRED_FIELDS = (
    "symbol", "exchange", "market", "trade_date",
    "open", "high", "low", "close", "adjust_type", "source", "ingested_at",
)
DAILY_BAR_PRICE_FIELDS = ("open", "high", "low", "close")
DAILY_BAR_TURNOVER_FIELDS = ("volume", "amount")


class DataQualityService:
    def __init__(self, db: Session, *, lake_root: str | Path | None = None) -> None:
        self.db = db
        self.lake_root = lake_root

    def get_overview(self) -> dict:
        datasets = list(self.db.scalars(select(Dataset)).all())
        for dataset in datasets:
            sync_projected_dataset_row_count(self.db, dataset)
        self.db.commit()
        reports_total = self.db.scalar(select(func.count(DataQualityReport.id))) or 0
        reports_warning = self.db.scalar(
            select(func.count(DataQualityReport.id)).where(DataQualityReport.severity == "warning")
        ) or 0
        reports_error = self.db.scalar(
            select(func.count(DataQualityReport.id)).where(DataQualityReport.severity == "error")
        ) or 0
        latest_checked_at = self.db.scalar(select(func.max(DataQualityReport.checked_at)))
        datasets_good = sum(1 for d in datasets if d.quality_status == "good")
        datasets_warning = sum(1 for d in datasets if d.quality_status == "warning")
        datasets_error = sum(1 for d in datasets if d.quality_status == "error")
        return {
            "datasets_total": len(datasets),
            "datasets_good": datasets_good,
            "datasets_warning": datasets_warning,
            "datasets_error": datasets_error,
            "datasets_unknown": len(datasets) - datasets_good - datasets_warning - datasets_error,
            "reports_total": reports_total,
            "reports_warning": reports_warning,
            "reports_error": reports_error,
            "latest_checked_at": latest_checked_at,
        }

    def list_reports(
        self,
        *,
        dataset_name: str | None,
        status: str | None,
        severity: str | None,
        checked_at: datetime | None,
        page: int,
        page_size: int,
    ) -> dict:
        conditions = []
        selected_checked_at = checked_at or self.db.scalar(select(func.max(DataQualityReport.checked_at)))
        if selected_checked_at is not None:
            conditions.append(DataQualityReport.checked_at == selected_checked_at)
        if dataset_name:
            conditions.append(DataQualityReport.dataset_name.ilike(f"%{dataset_name.strip()}%"))
        if status:
            conditions.append(DataQualityReport.status == status.strip())
        if severity:
            conditions.append(DataQualityReport.severity == severity.strip())
        total_stmt = select(func.count(DataQualityReport.id))
        records_stmt = select(DataQualityReport).order_by(
            DataQualityReport.checked_at.desc(), DataQualityReport.id.desc(),
        )
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)
        total = self.db.scalar(total_stmt) or 0
        reports = list(self.db.scalars(records_stmt.offset((page - 1) * page_size).limit(page_size)).all())
        return {
            "items": self._serialize_reports(reports),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size) if total else 0,
            "checked_at": selected_checked_at,
        }

    def list_check_runs(self, *, limit: int = 10) -> dict:
        checked_times = list(self.db.scalars(
            select(DataQualityReport.checked_at)
            .group_by(DataQualityReport.checked_at)
            .order_by(DataQualityReport.checked_at.desc())
            .limit(limit)
        ).all())
        if not checked_times:
            return {"items": []}
        reports = list(self.db.scalars(
            select(DataQualityReport)
            .where(DataQualityReport.checked_at.in_(checked_times))
            .order_by(DataQualityReport.checked_at.desc(), DataQualityReport.id.desc())
        ).all())
        reports_by_checked_at: dict[datetime, list[DataQualityReport]] = defaultdict(list)
        for report in reports:
            reports_by_checked_at[report.checked_at].append(report)
        return {"items": [
            {
                "checked_at": ca,
                "reports_total": len(rr),
                "reports_warning": sum(1 for r in rr if r.severity == "warning"),
                "reports_error": sum(1 for r in rr if r.severity == "error"),
            }
            for ca, rr in [(ct, reports_by_checked_at.get(ct, [])) for ct in checked_times]
        ]}

    def run_check(self) -> dict:
        datasets = list(self.db.scalars(select(Dataset).order_by(Dataset.name.asc())).all())
        checked_at = datetime.utcnow()
        reports_created = 0
        for dataset in datasets:
            reports = self._check_dataset(dataset=dataset, checked_at=checked_at)
            for report in reports:
                self.db.add(report)
            reports_created += len(reports)
            dataset.quality_status = self._dataset_quality_status(reports)
        self.db.commit()
        return {
            "checked_datasets": len(datasets),
            "reports_created": reports_created,
            "checked_at": checked_at,
            "overview": self.get_overview(),
        }

    def _check_dataset(self, *, dataset: Dataset, checked_at: datetime) -> list[DataQualityReport]:
        reports: list[DataQualityReport] = []
        if dataset.row_count <= 0:
            reports.append(self._report(dataset, "row_count", "warning", "warning",
                "row_count", str(dataset.row_count), "> 0",
                f"数据集 {dataset.name} 暂无记录。", checked_at))
        if dataset.latest_data_date is None:
            reports.append(self._report(dataset, "freshness", "warning", "warning",
                "latest_data_date", None, "not null",
                f"数据集 {dataset.name} 缺少最新数据日期。", checked_at))
        if dataset.name == "daily_bars":
            reports.extend(self._check_daily_bars(dataset=dataset, checked_at=checked_at))
        if not reports:
            reports.append(self._report(dataset, "basic", "good", "info",
                "basic_integrity", "passed", "passed",
                f"数据集 {dataset.name} 通过基础目录和数据质量检查。", checked_at))
        return reports

    def _check_daily_bars(self, *, dataset: Dataset, checked_at: datetime) -> list[DataQualityReport]:
        reports: list[DataQualityReport] = []
        dataset_dir = Path(dataset.path) if dataset.path else None
        rows = DailyBarRepository(lake_root=self.lake_root, dataset_dir=dataset_dir).read_all()
        if not rows:
            if dataset.row_count > 0:
                reports.append(self._report(dataset, "storage_availability", "error", "error",
                    "daily_bars_rows_on_disk", "0", f">= {dataset.row_count}",
                    "数据目录显示日线数据存在，但 Parquet 存储中没有读到记录。", checked_at))
            return reports

        # field_completeness
        missing_count = sum(
            1 for row in rows for field in DAILY_BAR_REQUIRED_FIELDS if _is_missing(row.get(field))
        )
        if missing_count > 0:
            total_required = len(rows) * len(DAILY_BAR_REQUIRED_FIELDS)
            completeness = 1 - missing_count / total_required if total_required else 0
            reports.append(self._report(dataset, "field_completeness", "warning", "warning",
                "required_field_completeness", f"{completeness:.2%}", "100%",
                f"日线数据有 {missing_count} 个必填字段为空。", checked_at))

        # duplicate
        keys = [
            (row.get("symbol"), row.get("exchange"), row.get("market"),
             row.get("trade_date"), row.get("adjust_type"))
            for row in rows
            if not any(_is_missing(row.get(f)) for f in ("symbol", "exchange", "market", "trade_date", "adjust_type"))
        ]
        duplicate_count = sum(c - 1 for c in Counter(keys).values() if c > 1)
        if duplicate_count > 0:
            reports.append(self._report(dataset, "duplicate_record", "error", "error",
                "duplicate_primary_keys", str(duplicate_count), "0",
                f"日线数据存在 {duplicate_count} 条重复主键记录。", checked_at))

        # prices
        negative_price_count = 0
        high_low_errors = 0
        high_bound_errors = 0
        low_bound_errors = 0
        negative_turnover_count = 0
        for row in rows:
            prices = {f: _as_float(row.get(f)) for f in DAILY_BAR_PRICE_FIELDS}
            negative_price_count += sum(1 for v in prices.values() if v is not None and v < 0)
            op, hi, lo, cl = prices["open"], prices["high"], prices["low"], prices["close"]
            if hi is not None and lo is not None and hi < lo:
                high_low_errors += 1
            if hi is not None and any(v is not None and hi < v for v in (op, cl)):
                high_bound_errors += 1
            if lo is not None and any(v is not None and lo > v for v in (op, cl)):
                low_bound_errors += 1
            negative_turnover_count += sum(
                1 for f in DAILY_BAR_TURNOVER_FIELDS
                if (v := _as_float(row.get(f))) is not None and v < 0
            )
        if negative_price_count:
            reports.append(self._report(dataset, "negative_price", "error", "error",
                "negative_ohlc_fields", str(negative_price_count), "0",
                f"OHLC 价格字段中有 {negative_price_count} 个负值。", checked_at))
        if high_low_errors:
            reports.append(self._report(dataset, "ohlc_range", "error", "error",
                "high_lower_than_low", str(high_low_errors), "0",
                f"有 {high_low_errors} 条日线记录不满足 high >= low。", checked_at))
        if high_bound_errors:
            reports.append(self._report(dataset, "ohlc_high_bound", "error", "error",
                "high_lower_than_open_or_close", str(high_bound_errors), "0",
                f"有 {high_bound_errors} 条日线记录不满足 high >= open/close。", checked_at))
        if low_bound_errors:
            reports.append(self._report(dataset, "ohlc_low_bound", "error", "error",
                "low_higher_than_open_or_close", str(low_bound_errors), "0",
                f"有 {low_bound_errors} 条日线记录不满足 low <= open/close。", checked_at))
        if negative_turnover_count:
            reports.append(self._report(dataset, "negative_turnover", "error", "error",
                "negative_volume_or_amount", str(negative_turnover_count), "0",
                f"成交量或成交额字段中有 {negative_turnover_count} 个负值。", checked_at))

        # missing_trade_dates
        trade_dates_by_market: dict[str, set[date]] = defaultdict(set)
        trade_dates_by_symbol: dict[tuple[str, str], set[date]] = defaultdict(set)
        trade_dates_by_market_adjustment: dict[tuple[str, str], set[date]] = defaultdict(set)
        trade_dates_by_symbol_adjustment: dict[tuple[str, str, str], set[date]] = defaultdict(set)
        for row in rows:
            market = row.get("market")
            symbol = row.get("symbol")
            trade_date = row.get("trade_date")
            if market and isinstance(trade_date, date):
                market_code = str(market)
                adjust_type = str(row.get("adjust_type") or "none")
                trade_dates_by_market[market_code].add(trade_date)
                trade_dates_by_market_adjustment[(market_code, adjust_type)].add(trade_date)
                if symbol:
                    symbol_code = str(symbol)
                    trade_dates_by_symbol[(market_code, symbol_code)].add(trade_date)
                    trade_dates_by_symbol_adjustment[(market_code, symbol_code, adjust_type)].add(trade_date)

        for market, actual_dates in sorted(trade_dates_by_market.items()):
            if not actual_dates:
                continue
            open_dates = self._open_calendar_dates(market=market, start_date=min(actual_dates), end_date=max(actual_dates))
            if not open_dates:
                continue
            missing_dates = [td for td in open_dates if td not in actual_dates]
            if not missing_dates:
                continue
            sample = "、".join(td.isoformat() for td in missing_dates[:5])
            reports.append(self._report(dataset, "missing_trade_date", "warning", "warning",
                f"{market}_missing_open_days", str(len(missing_dates)), "0",
                f"{market} 日线数据缺少 {len(missing_dates)} 个开市日行情，示例：{sample}。", checked_at))

        for (market, adjust_type), actual_dates in sorted(trade_dates_by_market_adjustment.items()):
            market_dates = trade_dates_by_market.get(market, set())
            if not actual_dates or not market_dates:
                continue
            open_dates = self._open_calendar_dates(
                market=market,
                start_date=min(market_dates),
                end_date=max(market_dates),
            )
            missing_dates = [td for td in open_dates if td not in actual_dates]
            if not missing_dates:
                continue
            sample = "、".join(td.isoformat() for td in missing_dates[:5])
            reports.append(self._report(
                dataset,
                "missing_trade_date_by_adjustment",
                "warning",
                "warning",
                f"{market}_{adjust_type}_missing_open_days",
                str(len(missing_dates)),
                "0",
                f"{market} {adjust_type} 日线数据缺少 {len(missing_dates)} 个开市日行情，示例：{sample}。",
                checked_at,
            ))

        missing_symbol_count = 0
        missing_day_count = 0
        samples: list[str] = []
        calendar_cache: dict[tuple[str, date, date], list[date]] = {}
        for (market, symbol), actual_dates in sorted(trade_dates_by_symbol.items()):
            market_dates = trade_dates_by_market.get(market, set())
            if not actual_dates or not market_dates:
                continue
            start_date, end_date = min(market_dates), max(market_dates)
            cache_key = (market, start_date, end_date)
            if cache_key not in calendar_cache:
                calendar_cache[cache_key] = self._open_calendar_dates(
                    market=market, start_date=start_date, end_date=end_date)
            open_dates = calendar_cache[cache_key]
            if not open_dates:
                continue
            missing_dates = [td for td in open_dates if td not in actual_dates]
            if not missing_dates:
                continue
            missing_symbol_count += 1
            missing_day_count += len(missing_dates)
            if len(samples) < 5:
                samples.append(f"{symbol}:{missing_dates[0].isoformat()}")
        if missing_symbol_count > 0:
            reports.append(self._report(dataset, "missing_trade_date_by_symbol", "warning", "warning",
                "symbols_missing_open_days",
                f"{missing_symbol_count} symbols / {missing_day_count} days", "0",
                f"有 {missing_symbol_count} 只股票缺少开市日行情，共缺 {missing_day_count} 个股票-交易日，示例：{'、'.join(samples)}。",
                checked_at))

        missing_adjustment_symbol_count = 0
        missing_adjustment_day_count = 0
        adjustment_samples: list[str] = []
        for (market, symbol, adjust_type), actual_dates in sorted(trade_dates_by_symbol_adjustment.items()):
            market_dates = trade_dates_by_market.get(market, set())
            if not actual_dates or not market_dates:
                continue
            start_date, end_date = min(market_dates), max(market_dates)
            cache_key = (market, start_date, end_date)
            if cache_key not in calendar_cache:
                calendar_cache[cache_key] = self._open_calendar_dates(
                    market=market, start_date=start_date, end_date=end_date)
            missing_dates = [td for td in calendar_cache[cache_key] if td not in actual_dates]
            if not missing_dates:
                continue
            missing_adjustment_symbol_count += 1
            missing_adjustment_day_count += len(missing_dates)
            if len(adjustment_samples) < 5:
                adjustment_samples.append(f"{symbol}/{adjust_type}:{missing_dates[0].isoformat()}")
        if missing_adjustment_symbol_count > 0:
            reports.append(self._report(
                dataset,
                "missing_trade_date_by_symbol_adjustment",
                "warning",
                "warning",
                "symbol_adjustments_missing_open_days",
                f"{missing_adjustment_symbol_count} symbol-adjustments / {missing_adjustment_day_count} days",
                "0",
                "有 "
                f"{missing_adjustment_symbol_count} 个股票-复权口径缺少开市日行情，"
                f"共缺 {missing_adjustment_day_count} 个股票-复权-交易日，示例：{'、'.join(adjustment_samples)}。",
                checked_at,
            ))

        # stock_pool_coverage
        covered_symbols_by_market: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            market = row.get("market")
            symbol = row.get("symbol")
            if not market:
                continue
            if symbol:
                covered_symbols_by_market[str(market)].add(str(symbol))
        for market, actual_dates in sorted(trade_dates_by_market.items()):
            if not actual_dates:
                continue
            open_dates = self._open_calendar_dates(market=market, start_date=min(actual_dates), end_date=max(actual_dates))
            if not open_dates:
                continue
            stock_symbols = set(self.db.scalars(
                select(Stock.symbol).where(Stock.market == market, Stock.status == "LISTED")
            ).all())
            if not stock_symbols:
                continue
            missing_symbols = sorted(stock_symbols - covered_symbols_by_market.get(market, set()))
            if not missing_symbols:
                continue
            missing_symbol_days = len(missing_symbols) * len(open_dates)
            sample = "、".join(missing_symbols[:5])
            reports.append(self._report(dataset, "stock_pool_missing_daily_bars", "warning", "warning",
                f"{market}_listed_symbols_without_daily_bars",
                f"{len(missing_symbols)} symbols / {missing_symbol_days} symbol-days", "0",
                f"{market} 股票池中有 {len(missing_symbols)} 只已上市股票在当前日线窗口完全没有行情，"
                f"共缺 {missing_symbol_days} 个股票-交易日，示例：{sample}。",
                checked_at))
        return reports

    def _open_calendar_dates(self, *, market: str, start_date: date, end_date: date) -> list[date]:
        return list(self.db.scalars(
            select(TradingCalendar.trade_date)
            .where(
                TradingCalendar.market == market,
                TradingCalendar.trade_date >= start_date,
                TradingCalendar.trade_date <= end_date,
                TradingCalendar.is_open.is_(True),
            )
            .order_by(TradingCalendar.trade_date.asc())
        ).all())

    @staticmethod
    def _dataset_quality_status(reports: list[DataQualityReport]) -> str:
        if any(r.severity == "error" for r in reports):
            return "error"
        if any(r.severity == "warning" for r in reports):
            return "warning"
        return "good"

    @staticmethod
    def _report(
        dataset: Dataset, check_type: str, status: str, severity: str,
        metric_name: str, metric_value: str | None, expected_value: str | None,
        message: str, checked_at: datetime,
    ) -> DataQualityReport:
        return DataQualityReport(
            dataset_name=dataset.name, check_type=check_type, status=status,
            severity=severity, metric_name=metric_name, metric_value=metric_value,
            expected_value=expected_value, message=message, checked_at=checked_at,
        )

    def _serialize_reports(self, reports: list[DataQualityReport]) -> list[dict]:
        if not reports:
            return []
        dataset_names = sorted({r.dataset_name for r in reports})
        datasets = {
            d.name: d
            for d in self.db.scalars(select(Dataset).where(Dataset.name.in_(dataset_names))).all()
        }
        latest_batches: dict[str, IngestBatch] = {}
        batches = self.db.scalars(
            select(IngestBatch)
            .where(IngestBatch.dataset_name.in_(dataset_names))
            .order_by(IngestBatch.dataset_name.asc(), IngestBatch.started_at.desc(), IngestBatch.id.desc())
        ).all()
        for batch in batches:
            latest_batches.setdefault(batch.dataset_name, batch)
        return [
            {
                "id": r.id,
                "dataset_name": r.dataset_name,
                "check_type": r.check_type,
                "status": r.status,
                "severity": r.severity,
                "metric_name": r.metric_name,
                "metric_value": r.metric_value,
                "expected_value": r.expected_value,
                "message": r.message,
                "checked_at": r.checked_at,
                "trace": {
                    "dataset_source": ds.source if ds else None,
                    "storage_type": ds.storage_type if ds else None,
                    "row_count": project_dataset_row_count(self.db, ds) if ds else None,
                    "latest_data_date": ds.latest_data_date if ds else None,
                    "quality_status": ds.quality_status if ds else None,
                    "schema_fields_count": len(ds.schema_json or {}) if ds else None,
                    "primary_keys_json": ds.primary_keys_json if ds else [],
                    "partition_keys_json": ds.partition_keys_json if ds else [],
                    "latest_batch_id": lb.id if lb else None,
                    "latest_task_id": lb.task_id if lb else None,
                    "latest_batch_source": lb.source if lb else None,
                    "latest_batch_requested_source": lb.requested_source if lb else None,
                    "latest_batch_market": lb.market if lb else None,
                    "latest_batch_symbol": lb.symbol if lb else None,
                    "latest_batch_start_date": lb.start_date if lb else None,
                    "latest_batch_end_date": lb.end_date if lb else None,
                    "latest_batch_status": lb.status if lb else None,
                    "latest_batch_schema_version": lb.schema_version if lb else None,
                    "latest_batch_normalize_version": lb.normalize_version if lb else None,
                    "latest_batch_records_written": lb.records_written if lb else None,
                    "latest_batch_quality_status": lb.quality_status if lb else None,
                    "latest_batch_finished_at": lb.finished_at if lb else None,
                },
            }
            for r in reports
            for ds in [datasets.get(r.dataset_name)]
            for lb in [latest_batches.get(r.dataset_name)]
        ]


def _is_missing(value: object) -> bool:
    return value is None or value == ""


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
