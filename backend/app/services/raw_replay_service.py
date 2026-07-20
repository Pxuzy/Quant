from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.adapters.base import normalize_daily_bar_adjust_type
from backend.app.adapters.registry import AdapterRegistry, default_adapter_registry
from backend.app.models import RawArtifact, SyncTask
from backend.app.repositories.sync_tasks import SyncTaskRepository
from backend.app.services.raw_artifact_store import RawArtifactStore
from backend.app.services.sync_service import MarketDataSyncService


RAW_DAILY_BARS_REPLAY_TASK_TYPE = "daily_bars_raw_replay"


class RawDailyBarsReplayService:
    """Replay a stored daily-bars artifact without contacting a provider."""

    def __init__(self, db: Session, registry: AdapterRegistry | None = None) -> None:
        self.db = db
        self.registry = registry or default_adapter_registry()
        self.task_repo = SyncTaskRepository(db)

    def run_task(self, task_id: int) -> SyncTask:
        task = self.task_repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Sync task {task_id} does not exist.")
        if task.task_type != RAW_DAILY_BARS_REPLAY_TASK_TYPE:
            raise ValueError(f"Sync task {task_id} is not a {RAW_DAILY_BARS_REPLAY_TASK_TYPE} task.")
        if task.status != "pending":
            raise ValueError(f"Sync task {task_id} is {task.status}, expected pending.")
        if task.input_raw_artifact_id is None:
            raise ValueError(f"Sync task {task_id} is missing input_raw_artifact_id.")

        records_read = 0
        records_written = 0
        try:
            artifact = self.db.get(RawArtifact, task.input_raw_artifact_id)
            if artifact is None:
                raise ValueError(f"Raw artifact {task.input_raw_artifact_id} does not exist.")
            if artifact.status != "stored":
                raise RuntimeError(f"Raw artifact {artifact.id} has status '{artifact.status}', expected stored.")

            self.task_repo.mark_running(task)
            raw_store = RawArtifactStore()
            path = raw_store.resolve_uri(artifact.uri)
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != artifact.sha256:
                raise RuntimeError(f"Raw artifact checksum mismatch: {artifact.id}")
            if len(content) != artifact.byte_size:
                raise RuntimeError(f"Raw artifact byte size mismatch: {artifact.id}")

            envelope = RawArtifactStore.read(path)
            _validate_envelope_metadata(envelope, artifact)
            records = envelope["records"]
            if len(records) != artifact.row_count:
                raise RuntimeError(
                    f"Raw artifact row count mismatch: expected {artifact.row_count}, got {len(records)}"
                )
            records_read = len(records)
            self.task_repo.require_heartbeat(task)
            artifact_adjust_type = artifact.adjust_type or envelope.get("adjust_type")
            if not artifact_adjust_type:
                raise RuntimeError(f"Raw artifact {artifact.id} has no recorded adjust_type.")
            artifact_adjust_type = normalize_daily_bar_adjust_type(artifact_adjust_type)
            adapter = self.registry.get(artifact.source)
            adjust_type = normalize_daily_bar_adjust_type(task.adjust_type or "none")
            if adjust_type != artifact_adjust_type:
                raise ValueError(
                    f"Replay adjust_type '{adjust_type}' does not match raw artifact '{artifact_adjust_type}'; "
                    "offline replay cannot perform price adjustment."
                )
            start_date = artifact.start_date or task.start_date
            end_date = artifact.end_date or task.end_date
            if start_date is None or end_date is None:
                raise RuntimeError(f"Raw artifact {artifact.id} is missing date range.")
            normalized = [
                replace(record, adjust_type=adjust_type)
                for record in adapter.normalize_daily_bars(records)
            ]

            service = MarketDataSyncService(
                self.db,
                registry=self.registry,
                lake_root=raw_store.lake_root,
            )
            records_written = service.ingest_pipeline.write_normalized(
                normalized=normalized,
                raw_records_count=records_read,
                adapter=adapter,
                market=artifact.market or "A_SHARE",
                symbol=artifact.symbol or task.symbol or "",
                start_date=start_date,
                end_date=end_date,
                task=task,
                requested_source="replay",
                raw_artifact_id=artifact.id,
            )
            self.task_repo.require_heartbeat(task)
            service._publish_daily_bars_version(task=task, source="replay")
            self.task_repo.complete(task, records_read=records_read, records_written=records_written)
            self.task_repo.add_log(
                task,
                level="info",
                message="Raw daily bars replay completed.",
                payload={
                    "raw_artifact_id": artifact.id,
                    "source": artifact.source,
                    "records_read": records_read,
                    "records_written": records_written,
                    "adjust_type": adjust_type,
                },
            )
            self.db.commit()
            self.db.refresh(task)
            return task
        except Exception as exc:
            self.task_repo.fail(task, message=str(exc), records_read=records_read, records_written=records_written)
            self.task_repo.add_log(
                task,
                level="error",
                message="Raw daily bars replay failed.",
                payload={"raw_artifact_id": task.input_raw_artifact_id, "error": str(exc)},
            )
            self.db.commit()
            self.db.refresh(task)
            return task


def _validate_envelope_metadata(envelope: dict, artifact: RawArtifact) -> None:
    expected = {
        "dataset_name": artifact.dataset_name,
        "task_id": artifact.task_id,
        "source": artifact.source,
        "requested_source": artifact.requested_source,
        "market": artifact.market,
        "symbol": artifact.symbol,
        "start_date": artifact.start_date.isoformat() if artifact.start_date else None,
        "end_date": artifact.end_date.isoformat() if artifact.end_date else None,
        "adjust_type": artifact.adjust_type,
        "row_count": artifact.row_count,
    }
    for field, value in expected.items():
        if envelope.get(field) != value:
            raise RuntimeError(f"Raw artifact metadata mismatch for {field}: {artifact.id}")
