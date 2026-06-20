from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from math import ceil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.models import DataQualityReport, Dataset, IngestBatch, Stock, TradingCalendar
from apps.api.repositories.daily_bars import DailyBarRepository
from apps.api.services.dataset_row_count_projection import project_dataset_row_count, sync_projected_dataset_row_count


DAILY_BAR_REQUIRED_FIELDS = (
    "symbol",
    "exchange",
    "market",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "adjust_type",
    "source",
    "ingested_at",
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
        datasets_good = sum(1 for dataset in datasets if dataset.quality_status == "good")
        datasets_warning = sum(1 for dataset in datasets if dataset.quality_status == "warning")
        datasets_error = sum(1 for dataset in datasets if dataset.quality_status == "error")
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
            DataQualityReport.checked_at.desc(),
            DataQualityReport.id.desc(),
        )
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)

        total = self.db.scalar(total_stmt) or 0
        reports = list(self.db.scalars(records_stmt.offset((page - 1) * page_size).limit(page_size)).all())
        return {
            "items": self._report_reads(reports),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size) if total else 0,
            "checked_at": selected_checked_at,
        }

    def list_check_runs(self, *, limit: int = 10) -> dict:
        checked_times = list(
            self.db.scalars(
                select(DataQualityReport.checked_at)
                .group_by(DataQualityReport.checked_at)
                .order_by(DataQualityReport.checked_at.desc())
                .limit(limit)
            ).all()
        )
        if not checked_times:
            return {"items": []}

        reports = list(
            self.db.scalars(
                select(DataQualityReport)
                .where(DataQualityReport.checked_at.in_(checked_times))
                .order_by(DataQualityReport.checked_at.desc(), DataQualityReport.id.desc())
            ).all()
        )
        reports_by_checked_at: dict[datetime, list[DataQualityReport]] = defaultdict(list)
        for report in reports:
            reports_by_checked_at[report.checked_at].append(report)

        items = []
        for checked_at in checked_times:
            run_reports = reports_by_checked_at.get(checked_at, [])
            items.append(
                {
                    "checked_at": checked_at,
                    "reports_total": len(run_reports),
                    "reports_warning": sum(1 for report in run_reports if report.severity == "warning"),
                    "reports_error": sum(1 for report in run_reports if report.severity == "error"),
                }
            )
        return {"items": items}

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
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="row_count",
                    status="warning",
                    severity="warning",
                    metric_name="row_count",
                    metric_value=str(dataset.row_count),
                    expected_value="> 0",
                    message=f"数据集 {dataset.name} 暂无记录。",
                    checked_at=checked_at,
                )
            )

        if dataset.latest_data_date is None:
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="freshness",
                    status="warning",
                    severity="warning",
                    metric_name="latest_data_date",
                    metric_value=None,
                    expected_value="not null",
                    message=f"数据集 {dataset.name} 缺少最新数据日期。",
                    checked_at=checked_at,
                )
            )

        if dataset.name == "daily_bars":
            reports.extend(self._check_daily_bars(dataset=dataset, checked_at=checked_at))

        if not reports:
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="basic",
                    status="good",
                    severity="info",
                    metric_name="basic_integrity",
                    metric_value="passed",
                    expected_value="passed",
                    message=f"数据集 {dataset.name} 通过基础目录和数据质量检查。",
                    checked_at=checked_at,
                )
            )
        return reports

    def _check_daily_bars(self, *, dataset: Dataset, checked_at: datetime) -> list[DataQualityReport]:
        reports: list[DataQualityReport] = []
        dataset_dir = Path(dataset.path) if dataset.path else None
        rows = DailyBarRepository(lake_root=self.lake_root, dataset_dir=dataset_dir).read_all()
        if not rows:
            if dataset.row_count > 0:
                reports.append(
                    self._report(
                        dataset=dataset,
                        check_type="storage_availability",
                        status="error",
                        severity="error",
                        metric_name="daily_bars_rows_on_disk",
                        metric_value="0",
                        expected_value=f">= {dataset.row_count}",
                        message="数据目录显示日线数据存在，但 Parquet 存储中没有读到记录。",
                        checked_at=checked_at,
                    )
                )
            return reports

        reports.extend(self._check_daily_bar_fields(dataset=dataset, rows=rows, checked_at=checked_at))
        reports.extend(self._check_daily_bar_duplicates(dataset=dataset, rows=rows, checked_at=checked_at))
        reports.extend(self._check_daily_bar_prices(dataset=dataset, rows=rows, checked_at=checked_at))
        reports.extend(self._check_missing_trade_dates(dataset=dataset, rows=rows, checked_at=checked_at))
        reports.extend(self._check_stock_pool_daily_coverage(dataset=dataset, rows=rows, checked_at=checked_at))
        return reports

    def _check_daily_bar_fields(
        self,
        *,
        dataset: Dataset,
        rows: list[dict],
        checked_at: datetime,
    ) -> list[DataQualityReport]:
        missing_count = 0
        total_required = len(rows) * len(DAILY_BAR_REQUIRED_FIELDS)
        for row in rows:
            missing_count += sum(1 for field in DAILY_BAR_REQUIRED_FIELDS if _is_missing(row.get(field)))

        if missing_count == 0:
            return []

        completeness = 1 - missing_count / total_required if total_required else 0
        return [
            self._report(
                dataset=dataset,
                check_type="field_completeness",
                status="warning",
                severity="warning",
                metric_name="required_field_completeness",
                metric_value=f"{completeness:.2%}",
                expected_value="100%",
                message=f"日线数据有 {missing_count} 个必填字段为空。",
                checked_at=checked_at,
            )
        ]

    def _check_daily_bar_duplicates(
        self,
        *,
        dataset: Dataset,
        rows: list[dict],
        checked_at: datetime,
    ) -> list[DataQualityReport]:
        keys = [
            (row.get("symbol"), row.get("exchange"), row.get("market"), row.get("trade_date"), row.get("adjust_type"))
            for row in rows
            if not any(_is_missing(row.get(field)) for field in ("symbol", "exchange", "market", "trade_date", "adjust_type"))
        ]
        duplicate_count = sum(count - 1 for count in Counter(keys).values() if count > 1)
        if duplicate_count == 0:
            return []

        return [
            self._report(
                dataset=dataset,
                check_type="duplicate_record",
                status="error",
                severity="error",
                metric_name="duplicate_primary_keys",
                metric_value=str(duplicate_count),
                expected_value="0",
                message=f"日线数据存在 {duplicate_count} 条重复主键记录。",
                checked_at=checked_at,
            )
        ]

    def _check_daily_bar_prices(
        self,
        *,
        dataset: Dataset,
        rows: list[dict],
        checked_at: datetime,
    ) -> list[DataQualityReport]:
        negative_price_count = 0
        high_low_errors = 0
        high_bound_errors = 0
        low_bound_errors = 0
        negative_turnover_count = 0

        for row in rows:
            prices = {field: _as_float(row.get(field)) for field in DAILY_BAR_PRICE_FIELDS}
            negative_price_count += sum(1 for value in prices.values() if value is not None and value < 0)

            open_price = prices["open"]
            high_price = prices["high"]
            low_price = prices["low"]
            close_price = prices["close"]
            if high_price is not None and low_price is not None and high_price < low_price:
                high_low_errors += 1
            if high_price is not None and any(
                value is not None and high_price < value for value in (open_price, close_price)
            ):
                high_bound_errors += 1
            if low_price is not None and any(
                value is not None and low_price > value for value in (open_price, close_price)
            ):
                low_bound_errors += 1

            negative_turnover_count += sum(
                1
                for field in DAILY_BAR_TURNOVER_FIELDS
                if (value := _as_float(row.get(field))) is not None and value < 0
            )

        reports: list[DataQualityReport] = []
        if negative_price_count:
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="negative_price",
                    status="error",
                    severity="error",
                    metric_name="negative_ohlc_fields",
                    metric_value=str(negative_price_count),
                    expected_value="0",
                    message=f"OHLC 价格字段中有 {negative_price_count} 个负值。",
                    checked_at=checked_at,
                )
            )
        if high_low_errors:
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="ohlc_range",
                    status="error",
                    severity="error",
                    metric_name="high_lower_than_low",
                    metric_value=str(high_low_errors),
                    expected_value="0",
                    message=f"有 {high_low_errors} 条日线记录不满足 high >= low。",
                    checked_at=checked_at,
                )
            )
        if high_bound_errors:
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="ohlc_high_bound",
                    status="error",
                    severity="error",
                    metric_name="high_lower_than_open_or_close",
                    metric_value=str(high_bound_errors),
                    expected_value="0",
                    message=f"有 {high_bound_errors} 条日线记录不满足 high >= open/close。",
                    checked_at=checked_at,
                )
            )
        if low_bound_errors:
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="ohlc_low_bound",
                    status="error",
                    severity="error",
                    metric_name="low_higher_than_open_or_close",
                    metric_value=str(low_bound_errors),
                    expected_value="0",
                    message=f"有 {low_bound_errors} 条日线记录不满足 low <= open/close。",
                    checked_at=checked_at,
                )
            )
        if negative_turnover_count:
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="negative_turnover",
                    status="error",
                    severity="error",
                    metric_name="negative_volume_or_amount",
                    metric_value=str(negative_turnover_count),
                    expected_value="0",
                    message=f"成交量或成交额字段中有 {negative_turnover_count} 个负值。",
                    checked_at=checked_at,
                )
            )
        return reports

    def _check_missing_trade_dates(
        self,
        *,
        dataset: Dataset,
        rows: list[dict],
        checked_at: datetime,
    ) -> list[DataQualityReport]:
        trade_dates_by_market: dict[str, set[date]] = defaultdict(set)
        trade_dates_by_symbol: dict[tuple[str, str], set[date]] = defaultdict(set)
        for row in rows:
            market = row.get("market")
            symbol = row.get("symbol")
            trade_date = row.get("trade_date")
            if market and isinstance(trade_date, date):
                trade_dates_by_market[str(market)].add(trade_date)
                if symbol:
                    trade_dates_by_symbol[(str(market), str(symbol))].add(trade_date)

        reports: list[DataQualityReport] = []
        for market, actual_dates in sorted(trade_dates_by_market.items()):
            if not actual_dates:
                continue
            open_dates = self._open_calendar_dates(
                market=market,
                start_date=min(actual_dates),
                end_date=max(actual_dates),
            )
            if not open_dates:
                continue

            missing_dates = [trade_date for trade_date in open_dates if trade_date not in actual_dates]
            if not missing_dates:
                continue

            sample = "、".join(trade_date.isoformat() for trade_date in missing_dates[:5])
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="missing_trade_date",
                    status="warning",
                    severity="warning",
                    metric_name=f"{market}_missing_open_days",
                    metric_value=str(len(missing_dates)),
                    expected_value="0",
                    message=f"{market} 日线数据缺少 {len(missing_dates)} 个开市日行情，示例：{sample}。",
                    checked_at=checked_at,
                )
            )

        reports.extend(
            self._check_missing_trade_dates_by_symbol(
                dataset=dataset,
                trade_dates_by_market=trade_dates_by_market,
                trade_dates_by_symbol=trade_dates_by_symbol,
                checked_at=checked_at,
            )
        )
        return reports

    def _check_missing_trade_dates_by_symbol(
        self,
        *,
        dataset: Dataset,
        trade_dates_by_market: dict[str, set[date]],
        trade_dates_by_symbol: dict[tuple[str, str], set[date]],
        checked_at: datetime,
    ) -> list[DataQualityReport]:
        missing_symbol_count = 0
        missing_day_count = 0
        samples: list[str] = []

        calendar_cache: dict[tuple[str, date, date], list[date]] = {}
        for (market, symbol), actual_dates in sorted(trade_dates_by_symbol.items()):
            market_dates = trade_dates_by_market.get(market, set())
            if not actual_dates or not market_dates:
                continue

            start_date = min(market_dates)
            end_date = max(market_dates)
            cache_key = (market, start_date, end_date)
            if cache_key not in calendar_cache:
                calendar_cache[cache_key] = self._open_calendar_dates(
                    market=market,
                    start_date=start_date,
                    end_date=end_date,
                )

            open_dates = calendar_cache[cache_key]
            if not open_dates:
                continue

            missing_dates = [trade_date for trade_date in open_dates if trade_date not in actual_dates]
            if not missing_dates:
                continue

            missing_symbol_count += 1
            missing_day_count += len(missing_dates)
            if len(samples) < 5:
                samples.append(f"{symbol}:{missing_dates[0].isoformat()}")

        if missing_symbol_count == 0:
            return []

        return [
            self._report(
                dataset=dataset,
                check_type="missing_trade_date_by_symbol",
                status="warning",
                severity="warning",
                metric_name="symbols_missing_open_days",
                metric_value=f"{missing_symbol_count} symbols / {missing_day_count} days",
                expected_value="0",
                message=f"有 {missing_symbol_count} 只股票缺少开市日行情，共缺 {missing_day_count} 个股票-交易日，示例：{'、'.join(samples)}。",
                checked_at=checked_at,
            )
        ]

    def _check_stock_pool_daily_coverage(
        self,
        *,
        dataset: Dataset,
        rows: list[dict],
        checked_at: datetime,
    ) -> list[DataQualityReport]:
        trade_dates_by_market: dict[str, set[date]] = defaultdict(set)
        covered_symbols_by_market: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            market = row.get("market")
            symbol = row.get("symbol")
            trade_date = row.get("trade_date")
            if not market:
                continue
            market_code = str(market)
            if isinstance(trade_date, date):
                trade_dates_by_market[market_code].add(trade_date)
            if symbol:
                covered_symbols_by_market[market_code].add(str(symbol))

        reports: list[DataQualityReport] = []
        for market, actual_dates in sorted(trade_dates_by_market.items()):
            if not actual_dates:
                continue
            open_dates = self._open_calendar_dates(
                market=market,
                start_date=min(actual_dates),
                end_date=max(actual_dates),
            )
            if not open_dates:
                continue

            stock_symbols = set(
                self.db.scalars(
                    select(Stock.symbol).where(
                        Stock.market == market,
                        Stock.status == "LISTED",
                    )
                ).all()
            )
            if not stock_symbols:
                continue

            missing_symbols = sorted(stock_symbols - covered_symbols_by_market.get(market, set()))
            if not missing_symbols:
                continue

            missing_symbol_days = len(missing_symbols) * len(open_dates)
            samples = "、".join(missing_symbols[:5])
            reports.append(
                self._report(
                    dataset=dataset,
                    check_type="stock_pool_missing_daily_bars",
                    status="warning",
                    severity="warning",
                    metric_name=f"{market}_listed_symbols_without_daily_bars",
                    metric_value=f"{len(missing_symbols)} symbols / {missing_symbol_days} symbol-days",
                    expected_value="0",
                    message=(
                        f"{market} 股票池中有 {len(missing_symbols)} 只已上市股票在当前日线窗口完全没有行情，"
                        f"共缺 {missing_symbol_days} 个股票-交易日，示例：{samples}。"
                    ),
                    checked_at=checked_at,
                )
            )
        return reports

    def _open_calendar_dates(self, *, market: str, start_date: date, end_date: date) -> list[date]:
        return list(
            self.db.scalars(
                select(TradingCalendar.trade_date)
                .where(
                    TradingCalendar.market == market,
                    TradingCalendar.trade_date >= start_date,
                    TradingCalendar.trade_date <= end_date,
                    TradingCalendar.is_open.is_(True),
                )
                .order_by(TradingCalendar.trade_date.asc())
            ).all()
        )

    @staticmethod
    def _dataset_quality_status(reports: list[DataQualityReport]) -> str:
        if any(report.severity == "error" for report in reports):
            return "error"
        if any(report.severity == "warning" for report in reports):
            return "warning"
        return "good"

    @staticmethod
    def _report(
        *,
        dataset: Dataset,
        check_type: str,
        status: str,
        severity: str,
        metric_name: str,
        metric_value: str | None,
        expected_value: str | None,
        message: str,
        checked_at: datetime,
    ) -> DataQualityReport:
        return DataQualityReport(
            dataset_name=dataset.name,
            check_type=check_type,
            status=status,
            severity=severity,
            metric_name=metric_name,
            metric_value=metric_value,
            expected_value=expected_value,
            message=message,
            checked_at=checked_at,
        )

    def _report_reads(self, reports: list[DataQualityReport]) -> list[dict]:
        if not reports:
            return []

        dataset_names = sorted({report.dataset_name for report in reports})
        datasets = {
            dataset.name: dataset
            for dataset in self.db.scalars(select(Dataset).where(Dataset.name.in_(dataset_names))).all()
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
            self._report_read(
                report,
                dataset=datasets.get(report.dataset_name),
                latest_batch=latest_batches.get(report.dataset_name),
                projected_row_count=(
                    project_dataset_row_count(self.db, datasets[report.dataset_name])
                    if report.dataset_name in datasets
                    else None
                ),
            )
            for report in reports
        ]

    def _report_read(
        self,
        report: DataQualityReport,
        *,
        dataset: Dataset | None,
        latest_batch: IngestBatch | None,
        projected_row_count: int | None,
    ) -> dict:
        return {
            "id": report.id,
            "dataset_name": report.dataset_name,
            "check_type": report.check_type,
            "status": report.status,
            "severity": report.severity,
            "metric_name": report.metric_name,
            "metric_value": report.metric_value,
            "expected_value": report.expected_value,
            "message": report.message,
            "checked_at": report.checked_at,
            "trace": _report_trace(
                dataset=dataset,
                latest_batch=latest_batch,
                projected_row_count=projected_row_count,
            ),
        }


def _is_missing(value: object) -> bool:
    return value is None or value == ""


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _report_trace(
    *,
    dataset: Dataset | None,
    latest_batch: IngestBatch | None,
    projected_row_count: int | None,
) -> dict:
    return {
        "dataset_source": dataset.source if dataset else None,
        "storage_type": dataset.storage_type if dataset else None,
        "row_count": projected_row_count if dataset else None,
        "latest_data_date": dataset.latest_data_date if dataset else None,
        "quality_status": dataset.quality_status if dataset else None,
        "schema_fields_count": len(dataset.schema_json or {}) if dataset else None,
        "primary_keys_json": dataset.primary_keys_json if dataset else [],
        "partition_keys_json": dataset.partition_keys_json if dataset else [],
        "latest_batch_id": latest_batch.id if latest_batch else None,
        "latest_task_id": latest_batch.task_id if latest_batch else None,
        "latest_batch_source": latest_batch.source if latest_batch else None,
        "latest_batch_requested_source": latest_batch.requested_source if latest_batch else None,
        "latest_batch_market": latest_batch.market if latest_batch else None,
        "latest_batch_symbol": latest_batch.symbol if latest_batch else None,
        "latest_batch_start_date": latest_batch.start_date if latest_batch else None,
        "latest_batch_end_date": latest_batch.end_date if latest_batch else None,
        "latest_batch_status": latest_batch.status if latest_batch else None,
        "latest_batch_schema_version": latest_batch.schema_version if latest_batch else None,
        "latest_batch_normalize_version": latest_batch.normalize_version if latest_batch else None,
        "latest_batch_records_written": latest_batch.records_written if latest_batch else None,
        "latest_batch_quality_status": latest_batch.quality_status if latest_batch else None,
        "latest_batch_finished_at": latest_batch.finished_at if latest_batch else None,
    }
