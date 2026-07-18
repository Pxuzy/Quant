from __future__ import annotations

from dataclasses import replace
from datetime import date

from backend.app.adapters.base import StockDataSourceAdapter
from backend.app.models import SyncTask
from backend.app.repositories.daily_bars import DailyBarArchiveError, DailyBarRepository
from backend.app.repositories.datasets import DatasetRepository
from backend.app.repositories.ingest_batches import IngestBatchRepository
from backend.app.repositories.raw_artifacts import RawArtifactRepository
from backend.app.repositories.stocks import StockRepository
from backend.app.repositories.sync_tasks import SyncTaskRepository
from backend.app.services.raw_artifact_store import RawArtifactStore
from backend.app.services.database_integration_service import invalidate_coverage_cache
from scripts.data_loader import invalidate_data_cache
from backend.app.services.normalized_data_validation import validate_daily_bar_records


class DailyBarIngestPipeline:
    def __init__(
        self,
        *,
        task_repo: SyncTaskRepository,
        ingest_batch_repo: IngestBatchRepository,
        dataset_repo: DatasetRepository,
        daily_bar_repo: DailyBarRepository,
        stock_repo: StockRepository,
        task_adjust_type,
    ) -> None:
        self.task_repo = task_repo
        self.ingest_batch_repo = ingest_batch_repo
        self.raw_artifact_repo = RawArtifactRepository(task_repo.db)
        self.dataset_repo = dataset_repo
        self.daily_bar_repo = daily_bar_repo
        self.stock_repo = stock_repo
        self.task_adjust_type = task_adjust_type

    def sync_symbol(
        self,
        *,
        task: SyncTask,
        adapter: StockDataSourceAdapter,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> tuple[int, int]:
        adjust_type = self.task_adjust_type(task)
        raw_records = adapter.fetch_daily_bars(
            symbol=symbol,
            exchange=None,
            market=task.market or "A_SHARE",
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
        records_read = len(raw_records)
        self.task_repo.add_log(
            task,
            level="info",
            message="Raw daily bar records fetched.",
            payload={"source": adapter.code, "records": records_read, "adjust_type": adjust_type},
        )

        raw_metadata = RawArtifactStore(lake_root=self.daily_bar_repo.lake_root).persist(
            task_id=task.id,
            dataset_name="daily_bars",
            source=adapter.code,
            requested_source=task.source,
            market=task.market or "A_SHARE",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            records=raw_records,
        )
        raw_artifact = self.raw_artifact_repo.create_artifact(
            task=task,
            dataset_name="daily_bars",
            source=adapter.code,
            requested_source=task.source,
            market=task.market or "A_SHARE",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            metadata=raw_metadata,
        )

        market = task.market or "A_SHARE"
        normalized = [replace(record, adjust_type=adjust_type) for record in adapter.normalize_daily_bars(raw_records)]
        records_written = self.write_normalized(
            normalized=normalized,
            raw_records_count=records_read,
            adapter=adapter,
            market=market,
            task=task,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            raw_artifact_id=raw_artifact.id,
        )
        invalidate_coverage_cache((task.market or "A_SHARE").strip().upper())
        invalidate_data_cache("stocks")
        invalidate_data_cache("search")
        invalidate_data_cache("calendar")
        # 更新股票最新数据日期
        try:
            latest = self.daily_bar_repo.latest_trade_date(market=(task.market or "A_SHARE").strip().upper())
            if latest is not None:
                self.stock_repo.update_data_freshness(symbol=symbol, market=task.market or "A_SHARE", latest_data_date=latest)
        except Exception:
            pass  # best-effort, 不影响主流程
        return records_read, records_written

    def write_normalized(
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
        raw_artifact_id: int | None = None,
    ) -> int:
        validation_errors = validate_daily_bar_records(normalized, source=adapter.code, market=market)
        batch = None
        if task is not None:
            batch = self.ingest_batch_repo.create_batch(
                task=task,
                dataset_name="daily_bars",
                source=adapter.code,
                requested_source=requested_source or task.source,
                market=market,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                raw_artifact_id=raw_artifact_id,
                raw_records=raw_records_count,
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

        records_written = 0
        try:
            records_written = self.daily_bar_repo.write_many(normalized)
            total_rows = self.daily_bar_repo.count(market=market)
            latest_trade_date = self.daily_bar_repo.latest_trade_date(market=market)
            dataset = self.dataset_repo.upsert_daily_bars_dataset(
                source=adapter.code,
                row_count=total_rows,
                latest_data_date=latest_trade_date,
                path=str(self.daily_bar_repo.dataset_dir),
            )
            if batch is not None:
                self.ingest_batch_repo.complete_batch(
                    batch,
                    records_written=records_written,
                    quality_status=dataset.quality_status,
                )
        except Exception as exc:
            if isinstance(exc, DailyBarArchiveError):
                records_written = exc.records_written
            if batch is not None:
                if records_written > 0:
                    self.ingest_batch_repo.mark_reconcile_required(batch, message=str(exc))
                else:
                    self.ingest_batch_repo.fail_batch(batch, message=str(exc))
            raise
        return records_written
