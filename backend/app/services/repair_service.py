"""Data-repair methods for ``MarketDataSyncService``.

This module hosts the market-wide repair surface area of
:class:`MarketDataSyncService`.  The mixin pattern keeps the repair
concerns isolated while remaining a true part of the service class —
``MarketDataSyncService`` subclasses ``_MarketRepairMixin`` so all method
signatures and behaviors are preserved verbatim.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from backend.app.adapters.base import HealthCheckResult, StockDataSourceAdapter, normalize_daily_bar_adjust_type
from backend.app.models import SyncTask
from backend.app.repositories.ingest_batches import IngestBatchRepository
from backend.app.services.market_repair_planner import (
    DEFAULT_MARKET_REPAIR_START_POLICY,
    LISTING_DATE_START_POLICY,
    MarketRepairPlan,
    MarketRepairPlanner,
)
from backend.app.services.stock_sync_service import AUTO_SOURCE_CODE

from .pipeline import (
    DEFAULT_ADJUST_TYPE,
    DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
    MARKET_REPAIR_TASK_TYPE,
    MAX_MARKET_REPAIR_SYMBOLS,
)
if TYPE_CHECKING:
    from .sync_service import MarketDataSyncService


class _MarketRepairMixin:
    """Repair-related methods, mixed into :class:`MarketDataSyncService`.

    These methods rely on attributes set up by
    :meth:`MarketDataSyncService.__init__` (``db``, ``task_repo``,
    ``data_source_repo``, ``market_repair_planner``, ``ingest_pipeline``,
    ``stock_repo``, ``daily_bar_repo``, ``ingest_batch_repo``).
    """

    # ------------------------------------------------------------------ #
    # Public repair API                                                  #
    # ------------------------------------------------------------------ #

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
        start_policy: str = DEFAULT_MARKET_REPAIR_START_POLICY,
        adjust_type: str = DEFAULT_ADJUST_TYPE,
    ) -> SyncTask:
        self._validate_date_range(start_date=start_date, end_date=end_date)
        self._validate_market_repair_limit(max_symbols=max_symbols)
        start_policy_code = self._validate_market_repair_start_policy(start_policy=start_policy)
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        source_code = source.strip().lower()
        market_code = market.strip().upper()

        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("daily_bars", require_healthy=False)
            if not candidates:
                self.db.rollback()
                raise ValueError("No enabled data source supports daily_bars.")
            task = self._create_market_repair_task(
                source=AUTO_SOURCE_CODE,
                market=market_code,
                start_date=start_date,
                end_date=end_date,
                max_symbols=max_symbols,
                start_policy=start_policy_code,
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

        task = self._create_market_repair_task(
            source=source_code,
            market=market_code,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            start_policy=start_policy_code,
            adjust_type=adjust_type_code,
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
        start_policy: str = DEFAULT_MARKET_REPAIR_START_POLICY,
        adjust_type: str = DEFAULT_ADJUST_TYPE,
    ) -> dict:
        self._validate_date_range(start_date=start_date, end_date=end_date)
        self._validate_market_repair_limit(max_symbols=max_symbols)
        start_policy_code = self._validate_market_repair_start_policy(start_policy=start_policy)
        adjust_type_code = normalize_daily_bar_adjust_type(adjust_type)
        source_code = source.strip().lower()
        market_code = market.strip().upper()

        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("daily_bars", require_healthy=False)
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
            start_policy=start_policy_code,
            adjust_type=adjust_type_code,
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
            "start_policy": plan.start_policy,
            "adjust_type": plan.adjust_type,
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

    def run_market_daily_bars_repair(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        start_date: date,
        end_date: date,
        max_symbols: int = DEFAULT_MARKET_REPAIR_MAX_SYMBOLS,
        start_policy: str = DEFAULT_MARKET_REPAIR_START_POLICY,
        adjust_type: str = DEFAULT_ADJUST_TYPE,
    ) -> SyncTask:
        task = self.create_market_daily_bars_repair_task(
            source=source,
            market=market,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            start_policy=start_policy,
            adjust_type=adjust_type,
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

    # ------------------------------------------------------------------ #
    # Internal repair helpers                                            #
    # ------------------------------------------------------------------ #

    def _create_market_repair_task(
        self,
        *,
        source: str,
        market: str,
        start_date: date,
        end_date: date,
        max_symbols: int,
        start_policy: str,
        adjust_type: str,
        candidate_sources: list[str] | None = None,
    ) -> SyncTask:
        task = self.task_repo.create_task(
            task_type=MARKET_REPAIR_TASK_TYPE,
            source=source,
            market=market,
            symbol=None,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            start_policy=start_policy,
            adjust_type=adjust_type,
        )
        payload = {
            "source": source,
            "market": market,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "max_symbols": max_symbols,
            "start_policy": start_policy,
            "adjust_type": adjust_type,
        }
        if candidate_sources is not None:
            payload["candidate_sources"] = candidate_sources
        self.task_repo.add_log(task, level="info", message="Market daily bars repair task created.", payload=payload)
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
                    self._record_adapter_result(adapter.code, success=False, capability="daily_bars")
                    continue

                self.task_repo.complete(task, records_read=records_read, records_written=records_written)
                self._record_adapter_result(adapter.code, success=True, capability="daily_bars")
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

    def _repair_market_with_adapter(self, *, task: SyncTask, adapter: StockDataSourceAdapter) -> tuple[int, int]:
        health = adapter.health_check()
        self.data_source_repo.update_health(adapter.code, health)
        if not health.healthy:
            raise RuntimeError(health.message)
        if task.start_date is None or task.end_date is None:
            raise RuntimeError("Market repair task is missing date range.")

        market = task.market or "A_SHARE"
        max_symbols = self._task_max_symbols(task)
        start_policy = self._task_start_policy(task)
        adjust_type = self._task_adjust_type(task)
        plan = self._build_market_repair_plan(
            adapter=adapter,
            market=market,
            start_date=task.start_date,
            end_date=task.end_date,
            max_symbols=max_symbols,
            start_policy=start_policy,
            adjust_type=adjust_type,
        )
        records_read, records_written, failed_count = self._repair_market_plan_with_adapter(task=task, adapter=adapter, plan=plan)
        return records_read, records_written

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
                "start_policy": plan.start_policy,
                "adjust_type": plan.adjust_type,
                "supported_exchanges": plan.supported_exchanges,
            },
        )

        if not plan.items:
            return 0, 0, 0

        from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
        from backend.app.core.config import get_settings

        parallelism = get_settings().repair_parallelism
        stock_timeout = 120

        adjust_type = plan.adjust_type
        market_name = plan.market

        # 并行 fetch（纯网络操作，无需 DB session）
        # 串行 write（需要 DB session，在主线程完成）
        self._refresh_deep_modules()
        executor = ThreadPoolExecutor(max_workers=parallelism)
        raw_results: dict[str, Future] = {}
        for item in plan.items:
            future = executor.submit(
                adapter.fetch_daily_bars,
                symbol=item.symbol,
                exchange=None,
                market=market_name,
                start_date=item.start_date,
                end_date=item.end_date,
                adjust_type=adjust_type,
            )
            raw_results[item.symbol] = (future, item)

        records_read = 0
        records_written = 0
        symbol_errors: list[str] = []

        try:
            for future in as_completed([f for f, _ in raw_results.values()], timeout=stock_timeout * 2):
                # 找到这个 future 对应的 item
                symbol_item = None
                for sym, (f, item) in raw_results.items():
                    if f is future:
                        symbol_item = item
                        break
                if symbol_item is None:
                    continue

                try:
                    raw_records = future.result(timeout=stock_timeout)
                except TimeoutError:
                    symbol_errors.append(f"{symbol_item.symbol}: Timed out after {stock_timeout}s")
                    self.task_repo.add_log(task, level="warning", message="Market repair symbol failed.",
                                           payload={"symbol": symbol_item.symbol, "error": "Timeout"})
                    self._record_failed_market_repair_batch(
                        task=task, adapter=adapter, market=market_name,
                        symbol=symbol_item.symbol, start_date=symbol_item.start_date,
                        end_date=symbol_item.end_date, message="Timeout")
                    continue
                except Exception as exc:
                    err = str(exc)
                    symbol_errors.append(f"{symbol_item.symbol}: {err}")
                    self.task_repo.add_log(task, level="warning", message="Market repair symbol failed.",
                                           payload={"symbol": symbol_item.symbol, "error": err[:200]})
                    self._record_failed_market_repair_batch(
                        task=task, adapter=adapter, market=market_name,
                        symbol=symbol_item.symbol, start_date=symbol_item.start_date,
                        end_date=symbol_item.end_date, message=err[:200])
                    continue

                # 串行写入（主线程，共享 self.db）
                try:
                    from dataclasses import replace

                    normalized = [replace(record, adjust_type=adjust_type)
                                  for record in adapter.normalize_daily_bars(raw_records)]
                    written = self.ingest_pipeline.write_normalized(
                        normalized=normalized,
                        raw_records_count=len(raw_records),
                        adapter=adapter,
                        market=market_name,
                        symbol=symbol_item.symbol,
                        start_date=symbol_item.start_date,
                        end_date=symbol_item.end_date,
                        task=task,
                        requested_source=adapter.code,
                    )
                    records_read += len(raw_records)
                    records_written += written
                    # 更新股票最新数据日期
                    try:
                        latest = self.daily_bar_repo.latest_trade_date(market=market_name)
                        if latest is not None:
                            self.stock_repo.update_data_freshness(
                                symbol=symbol_item.symbol, market=market_name, latest_data_date=latest)
                    except Exception:
                        pass
                except Exception as exc:
                    symbol_errors.append(f"{symbol_item.symbol}(write): {exc}")
                    self.task_repo.add_log(task, level="warning", message="Market repair symbol failed.",
                                           payload={"symbol": symbol_item.symbol, "error": str(exc)[:200]})

        finally:
            executor.shutdown(wait=False)

        self.task_repo.add_log(
            task, level="info",
            message="Market repair batch summary.",
            payload={"symbols_planned": len(plan.items),
                     "symbols_failed": len(symbol_errors),
                     "records_read": records_read,
                     "records_written": records_written},
        )

        if plan.items and records_written == 0 and symbol_errors:
            raise RuntimeError(f"Market daily bars repair wrote no records: {'; '.join(symbol_errors[:5])}")

        return records_read, records_written, len(symbol_errors)

    def _build_market_repair_plan(
        self,
        *,
        adapter: StockDataSourceAdapter,
        market: str,
        start_date: date,
        end_date: date,
        max_symbols: int,
        start_policy: str = DEFAULT_MARKET_REPAIR_START_POLICY,
        adjust_type: str = DEFAULT_ADJUST_TYPE,
    ) -> MarketRepairPlan:
        self._refresh_deep_modules()
        return self.market_repair_planner.build_plan(
            adapter=adapter,
            market=market,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            start_policy=start_policy,
            adjust_type=adjust_type,
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
    def _validate_market_repair_limit(*, max_symbols: int) -> None:
        if max_symbols < 1:
            raise ValueError("max_symbols must be greater than 0.")
        if max_symbols > MAX_MARKET_REPAIR_SYMBOLS:
            raise ValueError(f"max_symbols must be less than or equal to {MAX_MARKET_REPAIR_SYMBOLS}.")

    @staticmethod
    def _validate_market_repair_start_policy(*, start_policy: str) -> str:
        value = start_policy.strip().lower()
        if value not in {DEFAULT_MARKET_REPAIR_START_POLICY, LISTING_DATE_START_POLICY}:
            raise ValueError("start_policy must be requested_start or listing_date.")
        return value

    def _task_max_symbols(self, task: SyncTask) -> int:
        if task.max_symbols is not None:
            return int(task.max_symbols)
        return DEFAULT_MARKET_REPAIR_MAX_SYMBOLS

    def _task_start_policy(self, task: SyncTask) -> str:
        if task.start_policy:
            return self._validate_market_repair_start_policy(start_policy=task.start_policy)
        return DEFAULT_MARKET_REPAIR_START_POLICY


__all__ = ["_MarketRepairMixin"]
