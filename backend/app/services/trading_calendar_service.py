from __future__ import annotations

from datetime import date
from math import ceil

from sqlalchemy.orm import Session

from backend.app.adapters.base import HealthCheckResult, StockDataSourceAdapter
from backend.app.adapters.registry import AdapterRegistry, default_adapter_registry
from backend.app.models import SyncTask
from backend.app.repositories.data_sources import DataSourceRepository
from backend.app.repositories.datasets import DatasetRepository
from backend.app.repositories.ingest_batches import IngestBatchRepository
from backend.app.repositories.sync_tasks import SyncTaskRepository
from backend.app.repositories.trading_calendars import TradingCalendarRepository
from backend.app.services.database_integration_service import invalidate_coverage_cache
from backend.app.services.normalized_data_validation import validate_calendar_records
from backend.app.services.stock_sync_service import AUTO_SOURCE_CODE


class TradingCalendarService:
    def __init__(self, db: Session, registry: AdapterRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or default_adapter_registry()
        self.calendar_repo = TradingCalendarRepository(db)
        self.data_source_repo = DataSourceRepository(db)
        self.dataset_repo = DatasetRepository(db)
        self.ingest_batch_repo = IngestBatchRepository(db)
        self.task_repo = SyncTaskRepository(db)

    def list_days(
        self,
        *,
        market: str | None,
        start_date: date | None,
        end_date: date | None,
        is_open: bool | None,
        page: int,
        page_size: int,
    ) -> dict:
        items, total = self.calendar_repo.list_days(
            market=market,
            start_date=start_date,
            end_date=end_date,
            is_open=is_open,
            page=page,
            page_size=page_size,
        )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size) if total else 0,
        }

    def create_calendar_sync_task(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        start_date: date,
        end_date: date,
    ) -> SyncTask:
        self._validate_date_range(start_date=start_date, end_date=end_date)
        source_code = source.strip().lower()
        market_code = market.strip().upper()
        if source_code == AUTO_SOURCE_CODE:
            candidates = self._enabled_adapters_for_capability("calendars")
            if not candidates:
                self.db.rollback()
                raise ValueError("No enabled data source supports calendars.")
            task = self._create_calendar_task(
                source=AUTO_SOURCE_CODE,
                market=market_code,
                start_date=start_date,
                end_date=end_date,
                candidate_sources=[adapter.code for adapter in candidates],
            )
            self.db.commit()
            self.db.refresh(task)
            invalidate_coverage_cache(market_code)
            return task

        adapter = self.registry.get(source_code)
        if not adapter.capabilities().calendars:
            self.db.rollback()
            raise ValueError(f"Data source '{source_code}' does not support calendars.")

        data_source = self.data_source_repo.upsert_adapter(adapter)
        if not data_source.enabled:
            self.db.rollback()
            raise ValueError(f"Data source '{source_code}' is disabled.")

        task = self._create_calendar_task(source=source_code, market=market_code, start_date=start_date, end_date=end_date)
        self.db.commit()
        self.db.refresh(task)
        invalidate_coverage_cache(market_code)
        return task

    def run_calendar_sync_task(self, task_id: int) -> SyncTask:
        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Sync task {task_id} does not exist.")
        if task.task_type != "calendars":
            raise ValueError(f"Sync task {task_id} is not a calendars task.")
        if task.status != "pending":
            raise ValueError(f"Sync task {task_id} is {task.status}, expected pending.")
        if task.start_date is None or task.end_date is None:
            raise ValueError(f"Sync task {task_id} is missing date range.")

        if task.source == AUTO_SOURCE_CODE:
            return self._run_auto_calendar_sync_task(task)

        adapter = self.registry.get(task.source)
        data_source = self.data_source_repo.upsert_adapter(adapter)

        records_read = 0
        records_written = 0
        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Trading calendar sync started.",
                payload=self._task_payload(task, source=task.source),
            )
            if not data_source.enabled:
                raise RuntimeError(f"Data source '{task.source}' is disabled.")

            records_read, records_written = self._sync_with_adapter(task=task, adapter=adapter)
            self.task_repo.complete(task, records_read=records_read, records_written=records_written)
            self.task_repo.add_log(
                task,
                level="info",
                message="Trading calendar sync completed.",
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
            self.task_repo.add_log(
                task,
                level="error",
                message="Trading calendar sync failed.",
                payload={"error": str(exc)},
            )
            self.db.commit()
            self.db.refresh(task)
            return task

    def run_next_pending_calendar_sync(self) -> SyncTask | None:
        task = self.task_repo.get_next_pending_calendar_task()
        if task is None:
            return None
        return self.run_calendar_sync_task(task.id)

    def run_calendar_sync(
        self,
        *,
        source: str = AUTO_SOURCE_CODE,
        market: str = "A_SHARE",
        start_date: date,
        end_date: date,
    ) -> SyncTask:
        task = self.create_calendar_sync_task(
            source=source,
            market=market,
            start_date=start_date,
            end_date=end_date,
        )
        return self.run_calendar_sync_task(task.id)

    def _create_calendar_task(
        self,
        *,
        source: str,
        market: str,
        start_date: date,
        end_date: date,
        candidate_sources: list[str] | None = None,
    ) -> SyncTask:
        task = self.task_repo.create_task(
            task_type="calendars",
            source=source,
            market=market,
            start_date=start_date,
            end_date=end_date,
        )
        payload = {
            "source": source,
            "market": market,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        if candidate_sources is not None:
            payload["candidate_sources"] = candidate_sources
        self.task_repo.add_log(task, level="info", message="Trading calendar sync task created.", payload=payload)
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

    def _run_auto_calendar_sync_task(self, task: SyncTask) -> SyncTask:
        records_read = 0
        records_written = 0
        market = (task.market or "A_SHARE").strip().upper()
        candidates = self._enabled_adapters_for_capability("calendars")
        candidate_codes = [adapter.code for adapter in candidates]
        errors: list[str] = []

        try:
            self.task_repo.mark_running(task)
            self.task_repo.add_log(
                task,
                level="info",
                message="Trading calendar sync started.",
                payload={**self._task_payload(task, source=AUTO_SOURCE_CODE), "candidate_sources": candidate_codes},
            )
            if not candidates:
                raise RuntimeError("No enabled data source supports calendars.")

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
                    message="Trading calendar sync completed.",
                    payload={
                        "source": AUTO_SOURCE_CODE,
                        "selected_source": adapter.code,
                        "records_read": records_read,
                        "records_written": records_written,
                    },
                )
                self.db.commit()
                self.db.refresh(task)
                invalidate_coverage_cache(market)
                return task

            raise RuntimeError(f"All calendar data sources failed: {'; '.join(errors)}")
        except Exception as exc:
            self.task_repo.fail(task, message=str(exc), records_read=records_read, records_written=records_written)
            self.task_repo.add_log(
                task,
                level="error",
                message="Trading calendar sync failed.",
                payload={"error": str(exc)},
            )
            self.db.commit()
            self.db.refresh(task)
            invalidate_coverage_cache(market)
            return task

    def _sync_with_adapter(self, *, task: SyncTask, adapter: StockDataSourceAdapter) -> tuple[int, int]:
        health = adapter.health_check()
        self.data_source_repo.update_health(adapter.code, health)
        if not health.healthy:
            raise RuntimeError(health.message)
        if task.start_date is None or task.end_date is None:
            raise RuntimeError("Trading calendar task is missing date range.")

        market = (task.market or "A_SHARE").strip().upper()
        raw_records = adapter.fetch_trading_calendar(
            market=market,
            start_date=task.start_date,
            end_date=task.end_date,
        )
        records_read = len(raw_records)
        self.task_repo.add_log(
            task,
            level="info",
            message="Raw trading calendar records fetched.",
            payload={"source": adapter.code, "records": records_read},
        )

        normalized = adapter.normalize_trading_calendar(raw_records, market=market)
        validation_errors = validate_calendar_records(normalized, source=adapter.code, market=market)
        batch = self.ingest_batch_repo.create_batch(
            task=task,
            dataset_name="trading_calendars",
            source=adapter.code,
            requested_source=task.source,
            market=market,
            start_date=task.start_date,
            end_date=task.end_date,
            raw_records=records_read,
            normalized_records=len(normalized),
            validation_errors=validation_errors,
        )
        self.task_repo.add_log(
            task,
            level="info" if not validation_errors else "error",
            message="Normalized trading calendar records validated.",
            payload={
                "batch_id": batch.id,
                "source": adapter.code,
                "normalized_records": len(normalized),
                "validation_errors": validation_errors[:5],
            },
        )
        if validation_errors:
            raise RuntimeError(f"Trading calendar schema validation failed: {validation_errors[0]}")

        try:
            records_written = self.calendar_repo.upsert_many(normalized)
            total_rows = self.calendar_repo.count(market=market)
            latest_trade_date = self.calendar_repo.latest_trade_date(market=market)
            dataset = self.dataset_repo.upsert_trading_calendar_dataset(
                source=adapter.code,
                row_count=total_rows,
                latest_data_date=latest_trade_date,
            )
            self.ingest_batch_repo.complete_batch(batch, records_written=records_written, quality_status=dataset.quality_status)
        except Exception as exc:
            self.ingest_batch_repo.fail_batch(batch, message=str(exc))
            raise
        invalidate_coverage_cache(market)
        return records_read, records_written

    @staticmethod
    def _validate_date_range(*, start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date.")

    @staticmethod
    def _task_payload(task: SyncTask, *, source: str) -> dict:
        return {
            "source": source,
            "market": task.market,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "end_date": task.end_date.isoformat() if task.end_date else None,
        }
