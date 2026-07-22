"""Core market-data sync service.

This module hosts :class:`MarketDataSyncService` — the single-symbol daily
bars sync workflow — and the shared constants/helpers used by both the sync
and repair paths.  Repair-specific methods live in :mod:`repair_service`
and are mixed in via :class:`_MarketRepairMixin`.

Pipeline orchestration types (``DailyBarIngestPipeline``) are re-exported
from :mod:`pipeline` for callers that compose the sync stack.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.adapters.base import HealthCheckResult, StockDataSourceAdapter, normalize_daily_bar_adjust_type
from backend.app.adapters.registry import AdapterRegistry, default_adapter_registry
from backend.app.models import SyncTask
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.repositories.data_sources import DataSourceRepository
from backend.app.repositories.datasets import DatasetRepository
from backend.app.repositories.ingest_batches import IngestBatchRepository
from backend.app.repositories.stocks import StockRepository
from backend.app.repositories.sync_tasks import SyncTaskRepository
from backend.app.repositories.trading_calendars import TradingCalendarRepository
from backend.app.services.daily_bar_ingest_pipeline import DailyBarIngestPipeline
from backend.app.services.dataset_version_publisher import DatasetVersionPublisher
from backend.app.services.market_repair_planner import MarketRepairPlanner
from backend.app.services.stock_sync_service import AUTO_SOURCE_CODE

# Re-export pipeline surface for callers composing the sync stack.
from .pipeline import (  # noqa: F401
    DEFAULT_ADJUST_TYPE,
    DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
    MARKET_REPAIR_TASK_TYPE,
    MAX_MARKET_REPAIR_SYMBOLS,
    DailyBarIngestPipeline,
)
from .repair_service import _MarketRepairMixin


class MarketDataSyncService(_MarketRepairMixin):
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
        self.dataset_version_publisher = DatasetVersionPublisher(
            db,
            lake_root=self.daily_bar_repo.lake_root,
            source_repo=self.daily_bar_repo,
        )
        self.stock_repo = StockRepository(db)
        self.task_repo = SyncTaskRepository(db)
        self.trading_calendar_repo = TradingCalendarRepository(db)
        self.ingest_pipeline = DailyBarIngestPipeline(
            task_repo=self.task_repo,
            ingest_batch_repo=self.ingest_batch_repo,
            dataset_repo=self.dataset_repo,
            daily_bar_repo=self.daily_bar_repo,
            stock_repo=self.stock_repo,
            task_adjust_type=self._task_adjust_type,
        )
        self.market_repair_planner = MarketRepairPlanner(
            stock_repo=self.stock_repo,
            trading_calendar_repo=self.trading_calendar_repo,
            daily_bar_repo=self.daily_bar_repo,
        )

    def _refresh_deep_modules(self) -> None:
        self.ingest_pipeline.daily_bar_repo = self.daily_bar_repo
        self.market_repair_planner.daily_bar_repo = self.daily_bar_repo
        self.dataset_version_publisher.source_repo = self.daily_bar_repo

    def create_daily_bars_sync_task(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: str = DEFAULT_ADJUST_TYPE,
    ) -> SyncTask:
        self._validate_date_range(start_date=start_date, end_date=end_date)
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        source_code = source.strip().lower()
        symbol_code = symbol.strip()
        if not symbol_code:
            self.db.rollback()
            raise ValueError("第一阶段日线同步仅支持单只股票，请选择股票代码。")

        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("daily_bars", require_healthy=False)
            if not candidates:
                self.db.rollback()
                raise ValueError("No enabled data source supports daily_bars.")
            task = self._create_daily_task(
                source=AUTO_SOURCE_CODE,
                market=market,
                symbol=symbol_code,
                start_date=start_date,
                end_date=end_date,
                adjust_type=adjust_type_code,
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
            adjust_type=adjust_type_code,
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def run_next_pending_daily_bars_sync(self) -> SyncTask | None:
        task = self.task_repo.get_next_pending_daily_bars_task()
        if task is None:
            return None
        return self.run_daily_bars_sync_task(task.id)

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

            self.task_repo.require_heartbeat(task)
            records_read, records_written = self._sync_with_adapter(task=task, adapter=adapter)
            self.task_repo.require_heartbeat(task)
            self._publish_daily_bars_version(task=task, source=adapter.code)
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
        adjust_type: str = DEFAULT_ADJUST_TYPE,
    ) -> SyncTask:
        task = self.create_daily_bars_sync_task(
            source=source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
        return self.run_daily_bars_sync_task(task.id)

    def _create_daily_task(
        self,
        *,
        source: str,
        market: str,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust_type: str,
        candidate_sources: list[str] | None = None,
    ) -> SyncTask:
        task = self.task_repo.create_task(
            task_type="daily_bars",
            source=source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
        payload = {
            "source": source,
            "market": market,
            "symbol": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "adjust_type": adjust_type,
        }
        if candidate_sources is not None:
            payload["candidate_sources"] = candidate_sources
        self.task_repo.add_log(task, level="info", message="Daily bars sync task created.", payload=payload)
        return task

    def _enabled_adapters_for_capability(
        self,
        capability: str,
        *,
        require_healthy: bool = True,
    ) -> list[StockDataSourceAdapter]:
        self.data_source_repo.sync_registered_adapters(self.registry)
        candidates: list[StockDataSourceAdapter] = []
        for source in self.data_source_repo.list_enabled():
            try:
                adapter = self.registry.get(source.code)
            except ValueError:
                continue
            if require_healthy:
                health = adapter.health_check()
                self.data_source_repo.update_health(adapter.code, health)
                if not health.healthy:
                    continue
            if bool(getattr(adapter.capabilities(), capability, False)):
                candidates.append(adapter)

        # 智能排序：按历史成功率降序，成功率相同按静态 priority
        scored = []
        for adp in candidates:
            ds = self.data_source_repo.get_by_code(adp.code)
            rate = -1.0
            if ds is not None:
                cfg = ds.config_json if isinstance(ds.config_json, dict) else {}
                cap_stats = cfg.get("usage_stats", {}).get(capability, {})
                total = cap_stats.get("total", 0) or 0
                if total > 0:
                    rate = (cap_stats.get("success", 0) or 0) / total
            scored.append((rate, adp.priority, adp))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [item[2] for item in scored]

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
                    self.task_repo.require_heartbeat(task)
                    records_read, records_written = self._sync_with_adapter(task=task, adapter=adapter)
                    self.task_repo.require_heartbeat(task)
                    self._publish_daily_bars_version(task=task, source=adapter.code)
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
                    self._record_adapter_result(adapter.code, success=False, capability="daily_bars")
                    continue

                self.task_repo.complete(task, records_read=records_read, records_written=records_written)
                self._record_adapter_result(adapter.code, success=True, capability="daily_bars")
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

    def _sync_symbol_with_adapter(
        self,
        *,
        task: SyncTask,
        adapter: StockDataSourceAdapter,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[int, int]:
        self._refresh_deep_modules()
        return self.ingest_pipeline.sync_symbol(
            task=task,
            adapter=adapter,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def _write_normalized_daily_bars(
        self,
        *,
        normalized: list,
        raw_records_count: int,
        adapter: StockDataSourceAdapter,
        market: str,
        symbol: str,
        start_date: date,
        end_date: date,
        task: SyncTask | None = None,
        requested_source: str | None = None,
    ) -> int:
        self._refresh_deep_modules()
        return self.ingest_pipeline.write_normalized(
            normalized=normalized,
            raw_records_count=raw_records_count,
            adapter=adapter,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            task=task,
            requested_source=requested_source,
        )

    def _publish_daily_bars_version(self, *, task: SyncTask, source: str | None = None):
        self._refresh_deep_modules()
        self.task_repo.require_heartbeat(task)
        return self.dataset_version_publisher.publish_daily_bars(
            adjust_type=self._task_adjust_type(task),
            source=source or task.source,
        )

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

    @staticmethod
    def _validate_date_range(*, start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date.")
        if end_date > date.today():
            raise ValueError("date range cannot be in the future.")

    @staticmethod
    def _task_adjust_type(task: SyncTask) -> str:
        if task.adjust_type:
            return normalize_daily_bar_adjust_type(task.adjust_type)
        return DEFAULT_ADJUST_TYPE

    def _task_payload(self, task: SyncTask, *, source: str) -> dict:
        return {
            "source": source,
            "market": task.market,
            "symbol": task.symbol,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "end_date": task.end_date.isoformat() if task.end_date else None,
            "adjust_type": self._task_adjust_type(task),
        }

    def _record_adapter_result(self, code: str, *, success: bool, capability: str) -> None:
        """记录一次数据源调用结果到 config_json.usage_stats，用于动态排序。"""
        source = self.data_source_repo.get_by_code(code)
        if source is None:
            return
        config = source.config_json if isinstance(source.config_json, dict) else {}
        stats = config.get("usage_stats", {})
        cap_stats = stats.get(capability, {"total": 0, "success": 0})
        cap_stats["total"] = cap_stats.get("total", 0) + 1
        if success:
            cap_stats["success"] = cap_stats.get("success", 0) + 1
            cap_stats["last_success"] = datetime.now().isoformat()
        else:
            cap_stats["last_failure"] = datetime.now().isoformat()
        stats[capability] = cap_stats
        source.config_json = {**config, "usage_stats": stats}
        self.db.flush()


__all__ = [
    "DEFAULT_ADJUST_TYPE",
    "DEFAULT_MARKET_REPAIR_MAX_SYMBOLS",
    "MARKET_REPAIR_TASK_TYPE",
    "MAX_MARKET_REPAIR_SYMBOLS",
    "MarketDataSyncService",
]
