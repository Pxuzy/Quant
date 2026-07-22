from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import SyncTask
from backend.app.repositories.sync_tasks import SyncTaskRepository


class SyncTaskRunner:
    """Apply the common sync-task lifecycle and transaction boundaries."""

    def __init__(self, db: Session, *, task_repo: SyncTaskRepository) -> None:
        self.db = db
        self.task_repo = task_repo

    def start(self, task: SyncTask, *, message: str, payload: Mapping[str, Any] | None = None) -> None:
        self.task_repo.mark_running(task)
        self.task_repo.add_log(task, level="info", message=message, payload=dict(payload or {}))

    def succeed(
        self,
        task: SyncTask,
        *,
        message: str,
        records_read: int,
        records_written: int,
        payload: Mapping[str, Any] | None = None,
        failed_symbols: list[str] | None = None,
        failed_chunks: list[str] | None = None,
        failure_reason: str | None = None,
    ) -> SyncTask:
        self.task_repo.complete(
            task,
            records_read=records_read,
            records_written=records_written,
            failed_symbols=failed_symbols,
            failed_chunks=failed_chunks,
            failure_reason=failure_reason,
        )
        completion_payload = dict(payload or {})
        completion_payload.setdefault("records_read", records_read)
        completion_payload.setdefault("records_written", records_written)
        self.task_repo.add_log(task, level="info", message=message, payload=completion_payload)
        return self.commit(task)

    def fail(
        self,
        task: SyncTask,
        *,
        message: str,
        records_read: int,
        records_written: int,
        log_message: str,
    ) -> SyncTask:
        self.task_repo.fail(
            task,
            message=message,
            records_read=records_read,
            records_written=records_written,
        )
        self.task_repo.add_log(task, level="error", message=log_message, payload={"error": message})
        return self.commit(task)

    def commit(self, task: SyncTask) -> SyncTask:
        self.db.commit()
        self.db.refresh(task)
        return task

    def rollback(self) -> None:
        self.db.rollback()


__all__ = ["SyncTaskRunner"]
