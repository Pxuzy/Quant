from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from apps.api.adapters.base import HealthCheckResult, StockDataSourceAdapter
from apps.api.adapters.registry import AdapterRegistry, default_adapter_registry
from apps.api.core.market_symbols import is_common_stock_symbol
from apps.api.models import SyncTask
from apps.api.repositories.daily_bars import DailyBarRepository
from apps.api.repositories.data_sources import DataSourceRepository
from apps.api.repositories.datasets import DatasetRepository
from apps.api.repositories.ingest_batches import IngestBatchRepository
from apps.api.repositories.stocks import StockRepository
from apps.api.repositories.sync_tasks import SyncTaskRepository
from apps.api.repositories.trading_calendars import TradingCalendarRepository
from apps.api.services.database_integration_service import invalidate_coverage_cache
from apps.api.services.normalized_data_validation import validate_daily_bar_records
from apps.api.services.stock_sync_service import AUTO_SOURCE_CODE


MARKET_REPAIR_TASK_TYPE = "daily_bars_market_repair"
DEFAULT_MARKET_REPAIR_MAX_SYMBOLS = 20
MAX_MARKET_REPAIR_SYMBOLS = 200


@dataclass(frozen=True)
class MarketRepairPlanItem:
    symbol: str
    exchange: str
    name: str
    start_date: date
    end_date: date
    missing_trade_days: int


@dataclass(frozen=True)
class MarketRepairPlan:
    source: str
    market: str
    start_date: date
    end_date: date
    max_symbols: int
    stock_pool_count: int
    open_dates_count: int
    planned_missing_symbol_days: int
    supported_exchanges: list[str] | None
    items: list[MarketRepairPlanItem]

    @property
    def planned_symbols(self) -> int:
        return len(self.items)


class MarketDataSyncService:
    def __init__(
        self,
        db: Session,
        registry: AdapterRegistry | None = None,
        *,
        lake_root: str | Path | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or default_adapter_registry()
        self.data_source_repo = DataSourceRepository(db)
        self.dataset_repo = DatasetRepository(db)
        self.ingest_batch_repo = IngestBatchRepository(db)
        self.daily_bar_repo = DailyBarRepository(lake_root=lake_root)
        self.stock_repo = StockRepository(db)
        self.task_repo = SyncTaskRepository(db)
        self.trading_calendar_repo = TradingCalendarRepository(db)

    def create_daily_bars_sync_task(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> SyncTask:
        self._validate_date_range(start_date=start_date, end_date=end_date)
        source_code = source.strip().lower()
        symbol_code = symbol.strip()
        if not symbol_code:
            self.db.rollback()
            raise ValueError("第一阶段日线同步仅支持单只股票，请选择股票代码。")

        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("daily_bars")
            if not candidates:
                self.db.rollback()
                raise ValueError("No enabled data source supports daily_bars.")
            task = self._create_daily_task(
                source=AUTO_SOURCE_CODE,
                market=market,
                symbol=symbol_code,
                start_date=start_date,
                end_date=end_date,
                candidate_sources=[adapter.code for adapter in candidates],
            )
            self.db.commit()
            self.db.refresh(task)
            return task

        adapter = self.registry.get(source_code)
        if not adapter.capabilities().daily_bars:
            self.db.rollback()
            raise ValueError(f"Data source '{source_code}' does not support daily_bars.")

        data_source = self.data_source_repo.upsert_adapter(adapter)
        if not data_source.enabled:
            self.db.rollback()
            raise ValueError(f"Data source '{source_code}' is disabled.")

        task = self._create_daily_task(
            source=source_code,
            market=market,
            symbol=symbol_code,
            start_date=start_date,
            end_date=end_date,
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def run_next_pending_daily_bars_sync(self) -> SyncTask | None:
        task = self.task_repo.get_next_pending_daily_bars_task()
        if task is None:
            return None
        return self.run_daily_bars_sync_task(task.id)

    def run_next_pending_market_daily_bars_repair(self) -> SyncTask | None:
        task = self.task_repo.get_next_pending_market_daily_bars_repair_task()
        if task is None:
            return None
        return self.run_market_daily_bars_repair_task(task.id)

    def create_market_daily_bars_repair_task(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        start_date: date,
        end_date: date,
        max_symbols: int = DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
    ) -> SyncTask:
        self._validate_date_range(start_date=start_date, end_date=end_date)
        self._validate_market_repair_limit(max_symbols=max_symbols)
        source_code = source.strip().lower()
        market_code = market.strip().upper()

        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("daily_bars")
            if not candidates:
                self.db.rollback()
                raise ValueError("No enabled data source supports daily_bars.")
            task = self._create_market_repair_task(
                source=AUTO_SOURCE_CODE,
                market=market_code,
                start_date=start_date,
                end_date=end_date,
                max_symbols=max_symbols,
                candidate_sources=[adapter.code for adapter in candidates],
            )
            self.db.commit()
            self.db.refresh(task)
            return task

        adapter = self.registry.get(source_code)
        if not adapter.capabilities().daily_bars:
            self.db.rollback()
            raise ValueError(f"Data source '{source_code}' does not support daily_bars.")

        data_source = self.data_source_repo.upsert_adapter(adapter)
        if not data_source.enabled:
            self.db.rollback()
            raise ValueError(f"Data source '{source_code}' is disabled.")

        task = self._create_market_repair_task(
            source=source_code,
            market=market_code,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def preview_market_daily_bars_repair(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        start_date: date,
        end_date: date,
        max_symbols: int = DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
    ) -> dict:
        self._validate_date_range(start_date=start_date, end_date=end_date)
        self._validate_market_repair_limit(max_symbols=max_symbols)
        source_code = source.strip().lower()
        market_code = market.strip().upper()

        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("daily_bars")
            if not candidates:
                self.db.rollback()
                raise ValueError("No enabled data source supports daily_bars.")
            adapter = candidates[0]
            candidate_sources = [candidate.code for candidate in candidates]
        else:
            adapter = self.registry.get(source_code)
            if not adapter.capabilities().daily_bars:
                self.db.rollback()
                raise ValueError(f"Data source '{source_code}' does not support daily_bars.")

            data_source = self.data_source_repo.upsert_adapter(adapter)
            if not data_source.enabled:
                self.db.rollback()
                raise ValueError(f"Data source '{source_code}' is disabled.")
            candidate_sources = [adapter.code]

        plan = self._build_market_repair_plan(
            adapter=adapter,
            market=market_code,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
        )
        self.db.commit()
        return {
            "source": source_code,
            "selected_source": adapter.code,
            "candidate_sources": candidate_sources,
            "market": plan.market,
            "start_date": plan.start_date,
            "end_date": plan.end_date,
            "max_symbols": plan.max_symbols,
            "stock_pool_count": plan.stock_pool_count,
            "open_dates_count": plan.open_dates_count,
            "planned_symbols": plan.planned_symbols,
            "planned_missing_symbol_days": plan.planned_missing_symbol_days,
            "supported_exchanges": plan.supported_exchanges,
            "sample_items": [
                {
                    "symbol": item.symbol,
                    "exchange": item.exchange,
                    "name": item.name,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "missing_trade_days": item.missing_trade_days,
                }
                for item in plan.items
            ],
            "message": f"已生成补齐计划：{plan.planned_symbols} 只股票，预计缺口 {plan.planned_missing_symbol_days} 个交易日。",
        }

    def run_daily_bars_sync_task(self, task_id: int) -> SyncTask:
        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Sync task {task_id} does not exist.")
        if task.task_type != "daily_bars":
            raise ValueError(f"Sync task {task_id} is not a daily_bars task.")
        if task.status != "pending":
            raise ValueError(f"Sync task {task_id} is {task.status}, expected pending.")
        if task.symbol is None or task.start_date is None or task.end_date is None:
            raise ValueError(f"Sync task {task_id} is missing symbol or date range.")

        if task.source == AUTO_SOURCE_CODE:
            return self._run_auto_daily_bars_sync_task(task)

        adapter = self.registry.get(task.source)
        data_source = self.data_source_repo.upsert_adapter(adapter)

        records_read = 0
        records_written = 0
        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Daily bars sync started.",
                payload=self._task_payload(task, source=task.source),
            )
            if not data_source.enabled:
                raise RuntimeError(f"Data source '{task.source}' is disabled.")

            records_read, records_written = self._sync_with_adapter(task=task, adapter=adapter)
            self.task_repo.complete(task, records_read=records_read, records_written=records_written)
            self.task_repo.add_log(
                task,
                level="info",
                message="Daily bars sync completed.",
                payload={"records_read": records_read, "records_written": records_written},
            )
            self.db.commit()
            self.db.refresh(task)
            return task
        except Exception as exc:
            self.data_source_repo.update_health(
                task.source,
                HealthCheckResult(healthy=False, status="unhealthy", message=str(exc)),
            )
            self.task_repo.fail(task, message=str(exc), records_read=records_read, records_written=records_written)
            self.task_repo.add_log(task, level="error", message="Daily bars sync failed.", payload={"error": str(exc)})
            self.db.commit()
            self.db.refresh(task)
            return task

    def run_daily_bars_sync(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> SyncTask:
        task = self.create_daily_bars_sync_task(
            source=source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        return self.run_daily_bars_sync_task(task.id)

    def run_market_daily_bars_repair(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        start_date: date,
        end_date: date,
        max_symbols: int = DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
    ) -> SyncTask:
        task = self.create_market_daily_bars_repair_task(
            source=source,
            market=market,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
        )
        return self.run_market_daily_bars_repair_task(task.id)

    def run_market_daily_bars_repair_task(self, task_id: int) -> SyncTask:
        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Sync task {task_id} does not exist.")
        if task.task_type != MARKET_REPAIR_TASK_TYPE:
            raise ValueError(f"Sync task {task_id} is not a {MARKET_REPAIR_TASK_TYPE} task.")
        if task.status != "pending":
            raise ValueError(f"Sync task {task_id} is {task.status}, expected pending.")
        if task.start_date is None or task.end_date is None:
            raise ValueError(f"Sync task {task_id} is missing date range.")

        if task.source == AUTO_SOURCE_CODE:
            return self._run_auto_market_repair_task(task)

        adapter = self.registry.get(task.source)
        data_source = self.data_source_repo.upsert_adapter(adapter)
        records_read = 0
        records_written = 0
        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Market daily bars repair started.",
                payload=self._task_payload(task, source=task.source),
            )
            if not data_source.enabled:
                raise RuntimeError(f"Data source '{task.source}' is disabled.")

            records_read, records_written = self._repair_market_with_adapter(task=task, adapter=adapter)
            self.task_repo.complete(task, records_read=records_read, records_written=records_written)
            self.task_repo.add_log(
                task,
                level="info",
                message="Market daily bars repair completed.",
                payload={"records_read": records_read, "records_written": records_written},
            )
            self.db.commit()
            self.db.refresh(task)
            return task
        except Exception as exc:
            self.data_source_repo.update_health(
                task.source,
                HealthCheckResult(healthy=False, status="unhealthy", message=str(exc)),
            )
            self.task_repo.fail(task, message=str(exc), records_read=records_read, records_written=records_written)
            self.task_repo.add_log(task, level="error", message="Market daily bars repair failed.", payload={"error": str(exc)})
            self.db.commit()
            self.db.refresh(task)
            return task

    def _create_daily_task(
        self,
        *,
        source: str,
        market: str,
        symbol: str,
        start_date: date,
        end_date: date,
        candidate_sources: list[str] | None = None,
    ) -> SyncTask:
        task = self.task_repo.create_task(
            task_type="daily_bars",
            source=source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        payload = {
            "source": source,
            "market": market,
            "symbol": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        if candidate_sources is not None:
            payload["candidate_sources"] = candidate_sources
        self.task_repo.add_log(task, level="info", message="Daily bars sync task created.", payload=payload)
        return task

    def _create_market_repair_task(
        self,
        *,
        source: str,
        market: str,
        start_date: date,
        end_date: date,
        max_symbols: int,
        candidate_sources: list[str] | None = None,
    ) -> SyncTask:
        task = self.task_repo.create_task(
            task_type=MARKET_REPAIR_TASK_TYPE,
            source=source,
            market=market,
            symbol=None,
            start_date=start_date,
            end_date=end_date,
        )
        payload = {
            "source": source,
            "market": market,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "max_symbols": max_symbols,
        }
        if candidate_sources is not None:
            payload["candidate_sources"] = candidate_sources
        self.task_repo.add_log(task, level="info", message="Market daily bars repair task created.", payload=payload)
        return task

    def _enabled_adapters_for_capability(self, capability: str) -> list[StockDataSourceAdapter]:
        self.data_source_repo.sync_registered_adapters(self.registry)
        candidates: list[StockDataSourceAdapter] = []
        for source in self.data_source_repo.list_enabled():
            try:
                adapter = self.registry.get(source.code)
            except ValueError:
                continue
            if bool(getattr(adapter.capabilities(), capability, False)):
                candidates.append(adapter)
        return candidates

    def _run_auto_daily_bars_sync_task(self, task: SyncTask) -> SyncTask:
        records_read = 0
        records_written = 0
        candidates = self._enabled_adapters_for_capability("daily_bars")
        candidate_codes = [adapter.code for adapter in candidates]
        errors: list[str] = []

        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Daily bars sync started.",
                payload={**self._task_payload(task, source=AUTO_SOURCE_CODE), "candidate_sources": candidate_codes},
            )
            if not candidates:
                raise RuntimeError("No enabled data source supports daily_bars.")

            for adapter in candidates:
                self.task_repo.add_log(
                    task,
                    level="info",
                    message="Provider attempt started.",
                    payload={
                        "source": adapter.code,
                        "capabilities": adapter.capabilities().to_dict(),
                        "provider_metadata": adapter.metadata().to_dict(),
                    },
                )
                try:
                    records_read, records_written = self._sync_with_adapter(task=task, adapter=adapter)
                except Exception as exc:
                    error_message = str(exc)
                    errors.append(f"{adapter.code}: {error_message}")
                    self.data_source_repo.update_health(
                        adapter.code,
                        HealthCheckResult(healthy=False, status="unhealthy", message=error_message),
                    )
                    self.task_repo.add_log(
                        task,
                        level="warning",
                        message="Provider attempt failed.",
                        payload={"source": adapter.code, "error": error_message},
                    )
                    continue

                self.task_repo.complete(task, records_read=records_read, records_written=records_written)
                self.task_repo.add_log(
                    task,
                    level="info",
                    message="Daily bars sync completed.",
                    payload={
                        "source": AUTO_SOURCE_CODE,
                        "selected_source": adapter.code,
                        "records_read": records_read,
                        "records_written": records_written,
                    },
                )
                self.db.commit()
                self.db.refresh(task)
                return task

            raise RuntimeError(f"All daily-bars data sources failed: {'; '.join(errors)}")
        except Exception as exc:
            self.task_repo.fail(task, message=str(exc), records_read=records_read, records_written=records_written)
            self.task_repo.add_log(task, level="error", message="Daily bars sync failed.", payload={"error": str(exc)})
            self.db.commit()
            self.db.refresh(task)
            return task

    def _run_auto_market_repair_task(self, task: SyncTask) -> SyncTask:
        records_read = 0
        records_written = 0
        candidates = self._enabled_adapters_for_capability("daily_bars")
        candidate_codes = [adapter.code for adapter in candidates]
        errors: list[str] = []

        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Market daily bars repair started.",
                payload={**self._task_payload(task, source=AUTO_SOURCE_CODE), "candidate_sources": candidate_codes},
            )
            if not candidates:
                raise RuntimeError("No enabled data source supports daily_bars.")

            for adapter in candidates:
                self.task_repo.add_log(
                    task,
                    level="info",
                    message="Provider attempt started.",
                    payload={
                        "source": adapter.code,
                        "capabilities": adapter.capabilities().to_dict(),
                        "provider_metadata": adapter.metadata().to_dict(),
                    },
                )
                try:
                    records_read, records_written = self._repair_market_with_adapter(task=task, adapter=adapter)
                except Exception as exc:
                    error_message = str(exc)
                    errors.append(f"{adapter.code}: {error_message}")
                    self.data_source_repo.update_health(
                        adapter.code,
                        HealthCheckResult(healthy=False, status="unhealthy", message=error_message),
                    )
                    self.task_repo.add_log(
                        task,
                        level="warning",
                        message="Provider attempt failed.",
                        payload={"source": adapter.code, "error": error_message},
                    )
                    continue

                self.task_repo.complete(task, records_read=records_read, records_written=records_written)
                self.task_repo.add_log(
                    task,
                    level="info",
                    message="Market daily bars repair completed.",
                    payload={
                        "source": AUTO_SOURCE_CODE,
                        "selected_source": adapter.code,
                        "records_read": records_read,
                        "records_written": records_written,
                    },
                )
                self.db.commit()
                self.db.refresh(task)
                return task

            raise RuntimeError(f"All daily-bars data sources failed: {'; '.join(errors)}")
        except Exception as exc:
            self.task_repo.fail(task, message=str(exc), records_read=records_read, records_written=records_written)
            self.task_repo.add_log(task, level="error", message="Market daily bars repair failed.", payload={"error": str(exc)})
            self.db.commit()
            self.db.refresh(task)
            return task

    def _sync_with_adapter(self, *, task: SyncTask, adapter: StockDataSourceAdapter) -> tuple[int, int]:
        health = adapter.health_check()
        self.data_source_repo.update_health(adapter.code, health)
        if not health.healthy:
            raise RuntimeError(health.message)
        if task.symbol is None or task.start_date is None or task.end_date is None:
            raise RuntimeError("Daily bars task is missing symbol or date range.")

        return self._sync_symbol_with_adapter(
            task=task,
            adapter=adapter,
            symbol=task.symbol,
            start_date=task.start_date,
            end_date=task.end_date,
        )

    def _repair_market_with_adapter(self, *, task: SyncTask, adapter: StockDataSourceAdapter) -> tuple[int, int]:
        health = adapter.health_check()
        self.data_source_repo.update_health(adapter.code, health)
        if not health.healthy:
            raise RuntimeError(health.message)
        if task.start_date is None or task.end_date is None:
            raise RuntimeError("Market repair task is missing date range.")

        market = task.market or "A_SHARE"
        max_symbols = self._task_max_symbols(task)
        plan = self._build_market_repair_plan(
            adapter=adapter,
            market=market,
            start_date=task.start_date,
            end_date=task.end_date,
            max_symbols=max_symbols,
        )
        return self._repair_market_plan_with_adapter(task=task, adapter=adapter, plan=plan)

    def _repair_market_plan_with_adapter(
        self,
        *,
        task: SyncTask,
        adapter: StockDataSourceAdapter,
        plan: MarketRepairPlan,
    ) -> tuple[int, int]:
        market = plan.market
        self.task_repo.add_log(
            task,
            level="info",
            message="Market daily bars repair planned.",
            payload={
                "source": adapter.code,
                "market": plan.market,
                "stock_pool_count": plan.stock_pool_count,
                "open_dates_count": plan.open_dates_count,
                "planned_symbols": plan.planned_symbols,
                "planned_missing_symbol_days": plan.planned_missing_symbol_days,
                "max_symbols": plan.max_symbols,
                "supported_exchanges": plan.supported_exchanges,
            },
        )

        records_read = 0
        records_written = 0
        symbol_errors: list[str] = []
        for item in plan.items:
            self.task_repo.add_log(
                task,
                level="info",
                message="Market repair symbol started.",
                payload={
                    "source": adapter.code,
                    "symbol": item.symbol,
                    "start_date": item.start_date.isoformat(),
                    "end_date": item.end_date.isoformat(),
                    "missing_trade_days": item.missing_trade_days,
                },
            )
            try:
                symbol_read, symbol_written = self._sync_symbol_with_adapter(
                    task=task,
                    adapter=adapter,
                    symbol=item.symbol,
                    start_date=item.start_date,
                    end_date=item.end_date,
                )
            except Exception as exc:
                error_message = str(exc)
                symbol_errors.append(f"{item.symbol}: {error_message}")
                if not self._has_daily_bar_batch(
                    task=task,
                    adapter=adapter,
                    symbol=item.symbol,
                    start_date=item.start_date,
                    end_date=item.end_date,
                ):
                    self._record_failed_market_repair_batch(
                        task=task,
                        adapter=adapter,
                        market=market,
                        symbol=item.symbol,
                        start_date=item.start_date,
                        end_date=item.end_date,
                        message=error_message,
                    )
                self.task_repo.add_log(
                    task,
                    level="warning",
                    message="Market repair symbol failed.",
                    payload={
                        "source": adapter.code,
                        "symbol": item.symbol,
                        "start_date": item.start_date.isoformat(),
                        "end_date": item.end_date.isoformat(),
                        "missing_trade_days": item.missing_trade_days,
                        "error": error_message,
                    },
                )
                continue
            records_read += symbol_read
            records_written += symbol_written

        if plan.items and records_written == 0 and symbol_errors:
            raise RuntimeError(f"Market daily bars repair wrote no records: {'; '.join(symbol_errors)}")

        return records_read, records_written

    def _build_market_repair_plan(
        self,
        *,
        adapter: StockDataSourceAdapter,
        market: str,
        start_date: date,
        end_date: date,
        max_symbols: int,
    ) -> MarketRepairPlan:
        supported_exchanges = self._daily_bar_exchanges(adapter)
        stocks = [
            stock
            for stock in self.stock_repo.list_market_stocks(market=market, status="LISTED", common_only=True)
            if supported_exchanges is None or stock.exchange in supported_exchanges
            if is_common_stock_symbol(stock.symbol, stock.exchange, market)
        ]
        if not stocks:
            raise RuntimeError(f"股票池没有 {market} 已上市股票，请先同步股票池。")

        open_dates = self.trading_calendar_repo.open_dates(market=market, start_date=start_date, end_date=end_date)
        if not open_dates:
            raise RuntimeError("交易日历在该范围内没有开市日，请先同步交易日历。")

        existing_pairs = self.daily_bar_repo.market_symbol_trade_date_pairs(market=market)
        items: list[MarketRepairPlanItem] = []
        for stock in stocks:
            missing_dates = [trade_date for trade_date in open_dates if (stock.symbol, trade_date) not in existing_pairs]
            if not missing_dates:
                continue
            items.append(
                MarketRepairPlanItem(
                    symbol=stock.symbol,
                    exchange=stock.exchange,
                    name=stock.name,
                    start_date=min(missing_dates),
                    end_date=max(missing_dates),
                    missing_trade_days=len(missing_dates),
                )
            )
            if len(items) >= max_symbols:
                break

        return MarketRepairPlan(
            source=adapter.code,
            market=market,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            stock_pool_count=len(stocks),
            open_dates_count=len(open_dates),
            planned_missing_symbol_days=sum(item.missing_trade_days for item in items),
            supported_exchanges=sorted(supported_exchanges) if supported_exchanges is not None else None,
            items=items,
        )

    def _sync_symbol_with_adapter(
        self,
        *,
        task: SyncTask,
        adapter: StockDataSourceAdapter,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[int, int]:
        raw_records = adapter.fetch_daily_bars(
            symbol=symbol,
            exchange=None,
            market=task.market or "A_SHARE",
            start_date=start_date,
            end_date=end_date,
        )
        records_read = len(raw_records)
        self.task_repo.add_log(
            task,
            level="info",
            message="Raw daily bar records fetched.",
            payload={"source": adapter.code, "records": records_read},
        )

        normalized = adapter.normalize_daily_bars(raw_records)
        market = task.market or "A_SHARE"
        validation_errors = validate_daily_bar_records(normalized, source=adapter.code, market=market)
        batch = self.ingest_batch_repo.create_batch(
            task=task,
            dataset_name="daily_bars",
            source=adapter.code,
            requested_source=task.source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            raw_records=records_read,
            normalized_records=len(normalized),
            validation_errors=validation_errors,
        )
        self.task_repo.add_log(
            task,
            level="info" if not validation_errors else "error",
            message="Normalized daily bar records validated.",
            payload={
                "batch_id": batch.id,
                "source": adapter.code,
                "normalized_records": len(normalized),
                "validation_errors": validation_errors[:5],
            },
        )
        if validation_errors:
            raise RuntimeError(f"Daily bars schema validation failed: {validation_errors[0]}")

        try:
            records_written = self.daily_bar_repo.write_many(normalized)
            total_rows = self.daily_bar_repo.count(market=task.market)
            latest_trade_date = self.daily_bar_repo.latest_trade_date(market=task.market)
            dataset = self.dataset_repo.upsert_daily_bars_dataset(
                source=adapter.code,
                row_count=total_rows,
                latest_data_date=latest_trade_date,
                path=str(self.daily_bar_repo.dataset_dir),
            )
            self.ingest_batch_repo.complete_batch(batch, records_written=records_written, quality_status=dataset.quality_status)
        except Exception as exc:
            self.ingest_batch_repo.fail_batch(batch, message=str(exc))
            raise
        invalidate_coverage_cache((task.market or "A_SHARE").strip().upper())
        return records_read, records_written

    def _has_daily_bar_batch(
        self,
        *,
        task: SyncTask,
        adapter: StockDataSourceAdapter,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> bool:
        return any(
            batch.dataset_name == "daily_bars"
            and batch.source == adapter.code
            and batch.symbol == symbol
            and batch.start_date == start_date
            and batch.end_date == end_date
            for batch in self.ingest_batch_repo.list_for_task(task.id)
        )

    def _record_failed_market_repair_batch(
        self,
        *,
        task: SyncTask,
        adapter: StockDataSourceAdapter,
        market: str,
        symbol: str,
        start_date: date,
        end_date: date,
        message: str,
    ) -> None:
        batch = self.ingest_batch_repo.create_batch(
            task=task,
            dataset_name="daily_bars",
            source=adapter.code,
            requested_source=task.source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            raw_records=0,
            normalized_records=0,
            validation_errors=[],
        )
        self.ingest_batch_repo.fail_batch(batch, message=message)
        self.task_repo.add_log(
            task,
            level="warning",
            message="Market repair failed batch recorded.",
            payload={"batch_id": batch.id, "source": adapter.code, "symbol": symbol, "error": message},
        )

    @staticmethod
    def _validate_date_range(*, start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date.")

    @staticmethod
    def _validate_market_repair_limit(*, max_symbols: int) -> None:
        if max_symbols < 1:
            raise ValueError("max_symbols must be greater than 0.")
        if max_symbols > MAX_MARKET_REPAIR_SYMBOLS:
            raise ValueError(f"max_symbols must be less than or equal to {MAX_MARKET_REPAIR_SYMBOLS}.")

    def _task_max_symbols(self, task: SyncTask) -> int:
        for log in task.logs:
            payload = log.payload_json or {}
            if log.message == "Market daily bars repair task created." and "max_symbols" in payload:
                return int(payload["max_symbols"])
        return DEFAULT_MARKET_REPAIR_MAX_SYMBOLS

    @staticmethod
    def _daily_bar_exchanges(adapter: StockDataSourceAdapter) -> set[str] | None:
        exchanges = adapter.capabilities().daily_bar_exchanges
        if exchanges is None:
            return None
        return {exchange.strip().upper() for exchange in exchanges if exchange.strip()}

    @staticmethod
    def _task_payload(task: SyncTask, *, source: str) -> dict:
        return {
            "source": source,
            "market": task.market,
            "symbol": task.symbol,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "end_date": task.end_date.isoformat() if task.end_date else None,
        }
