from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from apps.api.adapters.base import HealthCheckResult, NormalizedStock, StockDataSourceAdapter
from apps.api.adapters.registry import AdapterRegistry, default_adapter_registry
from apps.api.core.market_symbols import is_common_stock_symbol
from apps.api.models import SyncTask
from apps.api.repositories.data_sources import DataSourceRepository
from apps.api.repositories.datasets import DatasetRepository
from apps.api.repositories.ingest_batches import IngestBatchRepository
from apps.api.repositories.stocks import StockRepository
from apps.api.repositories.sync_tasks import SyncTaskRepository
from apps.api.services.database_integration_service import invalidate_coverage_cache
from apps.api.services.normalized_data_validation import validate_stock_records


AUTO_SOURCE_CODE = "auto"
# Idempotency window: skip creating duplicate tasks within this window
IDEMPOTENCY_WINDOW_MINUTES = 5


class StockSyncService:
    def __init__(self, db: Session, registry: AdapterRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or default_adapter_registry()
        self.data_source_repo = DataSourceRepository(db)
        self.dataset_repo = DatasetRepository(db)
        self.ingest_batch_repo = IngestBatchRepository(db)
        self.stock_repo = StockRepository(db)
        self.task_repo = SyncTaskRepository(db)

    def create_stock_sync_task(self, *, source: str = AUTO_SOURCE_CODE, market: str = "A_SHARE") -> SyncTask:
        source_code = source.strip().lower()
        market_code = market.strip().upper()
        # Idempotency check: skip if a recent running/pending task exists
        existing_task = _find_recent_similar_task(
            task_repo=self.task_repo,
            task_type="stock_list",
            source=source_code,
            market=market_code,
        )
        if existing_task is not None:
            # If the task is still pending/running, return it — caller should use it as-is
            if existing_task.status in ("pending", "running"):
                self.task_repo.add_log(
                    existing_task,
                    level="info",
                    message="Duplicate sync task request skipped (idempotent).",
                    payload={"source": source_code, "market": market_code},
                )
                self.db.commit()
                return existing_task
            # If the task is already completed/failed, create a new one

        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("stock_list")
            if not candidates:
                self.db.rollback()
                raise ValueError("No enabled data source supports stock_list.")
            task = self.task_repo.create_task(task_type="stock_list", source=AUTO_SOURCE_CODE, market=market_code)
            self.task_repo.add_log(
                task,
                level="info",
                message="Stock list sync task created.",
                payload={
                    "source": AUTO_SOURCE_CODE,
                    "market": market_code,
                    "candidate_sources": [adapter.code for adapter in candidates],
                },
            )
            self.db.commit()
            self.db.refresh(task)
            return task

        adapter = self.registry.get(source_code)
        data_source = self.data_source_repo.upsert_adapter(adapter)
        if not data_source.enabled:
            self.db.rollback()
            raise ValueError(f"Data source '{source_code}' is disabled.")
        task = self.task_repo.create_task(task_type="stock_list", source=source_code, market=market_code)
        self.task_repo.add_log(
            task,
            level="info",
            message="Stock list sync task created.",
            payload={"source": source_code, "market": market_code},
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def run_next_pending_stock_sync(self) -> SyncTask | None:
        task = self.task_repo.get_next_pending_stock_task()
        if task is None:
            return None
        return self.run_stock_sync_task(task.id)

    def run_stock_sync_task(self, task_id: int) -> SyncTask:
        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Sync task {task_id} does not exist.")
        if task.task_type != "stock_list":
            raise ValueError(f"Sync task {task_id} is not a stock_list task.")
        if task.status != "pending":
            raise ValueError(f"Sync task {task_id} is {task.status}, expected pending.")

        source = task.source
        market = (task.market or "A_SHARE").strip().upper()
        if source == AUTO_SOURCE_CODE:
            return self._run_auto_stock_sync_task(task, market=market)

        adapter = self.registry.get(source)
        data_source = self.data_source_repo.upsert_adapter(adapter)

        records_read = 0
        records_written = 0
        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Stock list sync started.",
                payload={"source": source, "market": market},
            )
            if not data_source.enabled:
                raise RuntimeError(f"Data source '{source}' is disabled.")

            records_read, records_written = self._sync_with_adapter(task=task, adapter=adapter, market=market)

            self.task_repo.complete(task, records_read=records_read, records_written=records_written)
            self.task_repo.add_log(
                task,
                level="info",
                message="Stock list sync completed.",
                payload={"records_read": records_read, "records_written": records_written},
            )
            self.db.commit()
            self.db.refresh(task)
            invalidate_coverage_cache(market)
            return task
        except Exception as exc:
            self.data_source_repo.update_health(
                source,
                HealthCheckResult(healthy=False, status="unhealthy", message=str(exc)),
            )
            self.task_repo.fail(
                task,
                message=str(exc),
                records_read=records_read,
                records_written=records_written,
            )
            self.task_repo.add_log(task, level="error", message="Stock list sync failed.", payload={"error": str(exc)})
            self.db.commit()
            self.db.refresh(task)
            return task

    def run_stock_sync(self, *, source: str = AUTO_SOURCE_CODE, market: str = "A_SHARE") -> SyncTask:
        task = self.create_stock_sync_task(source=source, market=market)
        return self.run_stock_sync_task(task.id)

    def _enabled_adapters_for_capability(self, capability: str) -> list[StockDataSourceAdapter]:
        self.data_source_repo.sync_registered_adapters(self.registry)
        candidates: list[StockDataSourceAdapter] = []
        for source in self.data_source_repo.list_enabled():
            try:
                adapter = self.registry.get(source.code)
            except ValueError:
                continue
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

    def _run_auto_stock_sync_task(self, task: SyncTask, *, market: str) -> SyncTask:
        records_read = 0
        records_written = 0
        candidates = self._enabled_adapters_for_capability("stock_list")
        candidate_codes = [adapter.code for adapter in candidates]
        errors: list[str] = []

        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Stock list sync started.",
                payload={"source": AUTO_SOURCE_CODE, "market": market, "candidate_sources": candidate_codes},
            )
            if not candidates:
                raise RuntimeError("No enabled data source supports stock_list.")

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
                    records_read, records_written = self._sync_with_adapter(task=task, adapter=adapter, market=market)
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
                    self._record_adapter_result(adapter.code, success=False, capability="stock_list")
                    continue

                self.task_repo.complete(task, records_read=records_read, records_written=records_written)
                self.task_repo.add_log(
                    task,
                    level="info",
                    message="Stock list sync completed.",
                    payload={
                        "source": AUTO_SOURCE_CODE,
                        "selected_source": adapter.code,
                        "records_read": records_read,
                        "records_written": records_written,
                    },
                )
                self._record_adapter_result(adapter.code, success=True, capability="stock_list")
                self.db.commit()
                self.db.refresh(task)
                invalidate_coverage_cache(market)
                return task

            raise RuntimeError(f"All stock-list data sources failed: {'; '.join(errors)}")
        except Exception as exc:
            self.task_repo.fail(task, message=str(exc), records_read=records_read, records_written=records_written)
            self.task_repo.add_log(task, level="error", message="Stock list sync failed.", payload={"error": str(exc)})
            self.db.commit()
            self.db.refresh(task)
            return task

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

    def _sync_with_adapter(self, *, task: SyncTask, adapter: StockDataSourceAdapter, market: str) -> tuple[int, int]:
        health = adapter.health_check()
        self.data_source_repo.update_health(adapter.code, health)
        if not health.healthy:
            raise RuntimeError(health.message)

        raw_records = adapter.fetch_stock_list(market=market)
        records_read = len(raw_records)
        self.task_repo.add_log(
            task,
            level="info",
            message="Raw stock records fetched.",
            payload={"source": adapter.code, "records": records_read},
        )

        normalized = _listed_common_stock_records(adapter.normalize_stock_list(raw_records))
        validation_errors = validate_stock_records(normalized, source=adapter.code, market=market)
        batch = self.ingest_batch_repo.create_batch(
            task=task,
            dataset_name="stocks",
            source=adapter.code,
            requested_source=task.source,
            market=market,
            raw_records=records_read,
            normalized_records=len(normalized),
            validation_errors=validation_errors,
        )
        self.task_repo.add_log(
            task,
            level="info" if not validation_errors else "error",
            message="Normalized stock records validated.",
            payload={
                "batch_id": batch.id,
                "source": adapter.code,
                "normalized_records": len(normalized),
                "validation_errors": validation_errors[:5],
            },
        )
        if validation_errors:
            raise RuntimeError(f"Stock list schema validation failed: {validation_errors[0]}")

        try:
            records_written = self.stock_repo.upsert_many(normalized)
            total_rows = self.stock_repo.count(market=market, common_only=True)
            dataset = self.dataset_repo.upsert_stock_dataset(source=adapter.code, row_count=total_rows, latest_data_date=date.today())
            self.ingest_batch_repo.complete_batch(batch, records_written=records_written, quality_status=dataset.quality_status)
        except Exception as exc:
            self.ingest_batch_repo.fail_batch(batch, message=str(exc))
            raise
        return records_read, records_written


def _listed_common_stock_records(records: list[NormalizedStock]) -> list[NormalizedStock]:
    return [
        record
        for record in records
        if record.status == "LISTED" and is_common_stock_symbol(record.symbol, record.exchange, record.market)
    ]


def _find_recent_similar_task(
    task_repo: SyncTaskRepository,
    task_type: str,
    source: str,
    market: str,
    window_minutes: int = IDEMPOTENCY_WINDOW_MINUTES,
) -> SyncTask | None:
    """Find a recent running/pending task with the same type/source/market.
    
    Returns the existing task if found within the idempotency window,
    None otherwise.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    return task_repo.find_recent_task(
        task_type=task_type,
        source=source,
        market=market,
        statuses=["pending", "running"],
        created_after=cutoff,
    )
