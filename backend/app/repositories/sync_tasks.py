from __future__ import annotations

import os
import socket
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import SyncTask, SyncTaskLog


DEFAULT_LEASE_SECONDS = 1800


class SyncTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(
        self,
        *,
        task_type: str,
        source: str,
        market: str | None = None,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        max_symbols: int | None = None,
        start_policy: str | None = None,
        adjust_type: str | None = None,
        input_raw_artifact_id: int | None = None,
    ) -> SyncTask:
        task = SyncTask(
            task_type=task_type,
            source=source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            start_policy=start_policy,
            adjust_type=adjust_type,
            input_raw_artifact_id=input_raw_artifact_id,
        )
        self.db.add(task)
        self.db.flush()
        return task

    def get_task(self, task_id: int) -> SyncTask | None:
        return self.db.get(SyncTask, task_id)

    def list_task_logs(self, task_id: int) -> list[SyncTaskLog]:
        return list(
            self.db.scalars(
                select(SyncTaskLog)
                .where(SyncTaskLog.task_id == task_id)
                .order_by(SyncTaskLog.created_at.asc(), SyncTaskLog.id.asc())
            ).all()
        )

    def get_next_pending_stock_task(self) -> SyncTask | None:
        return self.get_next_pending_task("stock_list")

    def get_next_pending_daily_bars_task(self) -> SyncTask | None:
        return self.get_next_pending_task("daily_bars")

    def get_next_pending_market_daily_bars_repair_task(self) -> SyncTask | None:
        return self.get_next_pending_task("daily_bars_market_repair")

    def get_next_pending_calendar_task(self) -> SyncTask | None:
        return self.get_next_pending_task("calendars")

    def get_next_pending_task(self, task_type: str) -> SyncTask | None:
        return self.db.scalar(
            select(SyncTask)
            .where(
                SyncTask.task_type == task_type,
                SyncTask.status == "pending",
            )
            .order_by(SyncTask.created_at.asc(), SyncTask.id.asc())
            .limit(1)
        )

    def get_next_pending_any_task(self, task_types: Sequence[str]) -> SyncTask | None:
        if not task_types:
            return None
        return self.db.scalar(
            select(SyncTask)
            .where(
                SyncTask.task_type.in_(task_types),
                SyncTask.status == "pending",
            )
            .order_by(SyncTask.created_at.asc(), SyncTask.id.asc())
            .limit(1)
        )

    def latest_task_by_status(self, status: str) -> SyncTask | None:
        return self.db.scalar(
            select(SyncTask)
            .where(SyncTask.status == status)
            .order_by(
                SyncTask.finished_at.desc().nullslast(),
                SyncTask.started_at.desc().nullslast(),
                SyncTask.created_at.desc(),
                SyncTask.id.desc(),
            )
            .limit(1)
        )

    def current_running_task(self) -> SyncTask | None:
        return self.db.scalar(
            select(SyncTask)
            .where(SyncTask.status == "running")
            .order_by(
                SyncTask.started_at.asc().nullsfirst(),
                SyncTask.created_at.asc(),
                SyncTask.id.asc(),
            )
            .limit(1)
        )

    def mark_running(
        self,
        task: SyncTask,
        *,
        owner: str | None = None,
        lease_seconds: int = 1800,
    ) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be greater than 0")
        lease_owner = owner or f"{socket.gethostname()}:{os.getpid()}"
        started_at = datetime.now(timezone.utc)
        lease_expires_at = started_at + timedelta(seconds=lease_seconds)
        result = self.db.execute(
            update(SyncTask)
            .where(SyncTask.id == task.id, SyncTask.status == "pending")
            .values(
                status="running",
                progress=5,
                started_at=started_at,
                heartbeat_at=started_at,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                attempt=SyncTask.attempt + 1,
                failure_reason=None,
            )
        )
        if result.rowcount != 1:
            self.db.rollback()
            self.db.refresh(task)
            raise ValueError(f"Sync task {task.id} is {task.status}, expected pending.")
        self.db.flush()
        self.db.refresh(task)
        self.add_log(
            task,
            level="info",
            message="Sync task claimed by lightweight worker.",
            payload={
                "task_type": task.task_type,
                "source": task.source,
                "market": task.market,
                "symbol": task.symbol,
                "lease_owner": task.lease_owner,
                "lease_expires_at": task.lease_expires_at.isoformat() if task.lease_expires_at else None,
                "attempt": task.attempt,
            },
        )
        self.db.commit()
        self.db.refresh(task)
        task._lease_fence_owner = task.lease_owner
        task._lease_fence_attempt = task.attempt

    def heartbeat(
        self,
        task: SyncTask,
        *,
        owner: str,
        attempt: int | None = None,
        lease_seconds: int = 1800,
    ) -> bool:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be greater than 0")
        now = datetime.now(timezone.utc)
        conditions = [
            SyncTask.id == task.id,
            SyncTask.status == "running",
            SyncTask.lease_owner == owner,
        ]
        if attempt is not None:
            conditions.append(SyncTask.attempt == attempt)
        result = self.db.execute(
            update(SyncTask)
            .where(*conditions)
            .values(
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        self.db.flush()
        if result.rowcount != 1:
            return False
        self.db.refresh(task)
        return True

    def require_heartbeat(self, task: SyncTask, *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> None:
        owner = getattr(task, "_lease_fence_owner", task.lease_owner)
        attempt = getattr(task, "_lease_fence_attempt", task.attempt)
        if not owner or not self.heartbeat(
            task,
            owner=owner,
            attempt=attempt,
            lease_seconds=lease_seconds,
        ):
            self.db.rollback()
            raise RuntimeError(f"Sync task {task.id} lost its worker lease.")

    def complete(
        self,
        task: SyncTask,
        *,
        records_read: int,
        records_written: int,
        failed_symbols: list[str] | None = None,
        failed_chunks: list[str] | None = None,
        failure_reason: str | None = None,
    ) -> None:
        failed_symbols = list(dict.fromkeys(failed_symbols or []))
        failed_chunks = list(dict.fromkeys(failed_chunks or []))
        has_failures = bool(failed_symbols or failed_chunks or failure_reason)
        status = "partial_success" if has_failures and records_written > 0 else "failed" if has_failures else "success"
        owner = getattr(task, "_lease_fence_owner", task.lease_owner)
        attempt = getattr(task, "_lease_fence_attempt", task.attempt)
        result = self.db.execute(
            update(SyncTask)
            .where(
                SyncTask.id == task.id,
                SyncTask.status == "running",
                SyncTask.lease_owner == owner,
                SyncTask.attempt == attempt,
            )
            .values(
                status=status,
                progress=100,
                records_read=records_read,
                records_written=records_written,
                failed_symbols=failed_symbols,
                failed_chunks=failed_chunks,
                failure_reason=failure_reason,
                finished_at=datetime.now(timezone.utc),
                error_message=failure_reason if status == "failed" else None,
                heartbeat_at=None,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise RuntimeError(f"Sync task {task.id} lost its worker lease before completion.")
        self.db.flush()
        self.db.refresh(task)

    def fail(self, task: SyncTask, *, message: str, records_read: int = 0, records_written: int = 0) -> None:
        conditions = [SyncTask.id == task.id]
        owner = getattr(task, "_lease_fence_owner", None)
        attempt = getattr(task, "_lease_fence_attempt", None)
        if owner is not None and attempt is not None:
            conditions.extend(
                [
                    SyncTask.status == "running",
                    SyncTask.lease_owner == owner,
                    SyncTask.attempt == attempt,
                ]
            )
        else:
            conditions.append(SyncTask.status.in_(["pending", "running"]))
        result = self.db.execute(
            update(SyncTask)
            .where(*conditions)
            .values(
                status="failed",
                progress=100,
                records_read=records_read,
                records_written=records_written,
                failed_symbols=list(task.failed_symbols or []),
                failed_chunks=list(task.failed_chunks or []),
                failure_reason=message,
                error_message=message,
                finished_at=datetime.now(timezone.utc),
                heartbeat_at=None,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        if result.rowcount == 1:
            self.db.flush()
            self.db.refresh(task)

    def recover_stale_tasks(self, timeout_minutes: int = 30) -> int:
        """将运行超过 timeout_minutes 且仍为 running 状态的任务重置为 pending。

        用于 worker 崩溃恢复。返回恢复的任务数。
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=timeout_minutes)
        stale = list(
            self.db.scalars(
                select(SyncTask)
                .where(
                    SyncTask.status == "running",
                    (
                        (SyncTask.lease_expires_at.is_not(None) & (SyncTask.lease_expires_at < now))
                        | (SyncTask.lease_expires_at.is_(None) & (SyncTask.started_at < cutoff))
                    ),
                )
                .limit(50)
            ).all()
        )
        if not stale:
            return 0
        for task in stale:
            task.status = "pending"
            task.progress = 0
            task.lease_owner = None
            task.heartbeat_at = None
            task.lease_expires_at = None
            task.error_message = f"Auto-recovered from stale running state (started at {task.started_at})"
        self.db.flush()
        self.db.commit()
        return len(stale)

    def add_log(self, task: SyncTask, *, level: str, message: str, payload: dict | None = None) -> SyncTaskLog:
        log = SyncTaskLog(task_id=task.id, level=level, message=message, payload_json=payload)
        self.db.add(log)
        self.db.flush()
        return log

    def list_tasks(
        self,
        *,
        status: str | None,
        source: str | None,
        task_type: str | None = None,
        market: str | None = None,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[SyncTask], int]:
        conditions = []
        if status:
            conditions.append(SyncTask.status == status)
        if source:
            conditions.append(SyncTask.source == source)
        if task_type:
            conditions.append(SyncTask.task_type == task_type)
        if market:
            conditions.append(SyncTask.market == market)
        if symbol:
            conditions.append(SyncTask.symbol == symbol)
        if start_date:
            conditions.append(SyncTask.start_date >= start_date)
        if end_date:
            conditions.append(SyncTask.end_date <= end_date)

        total_stmt = select(func.count(SyncTask.id))
        records_stmt = select(SyncTask).order_by(SyncTask.created_at.desc(), SyncTask.id.desc())
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)

        total = self.db.scalar(total_stmt) or 0
        tasks = self.db.scalars(records_stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(tasks), total

    def count_by_status(self) -> dict[str, int]:
        rows = self.db.execute(select(SyncTask.status, func.count(SyncTask.id)).group_by(SyncTask.status)).all()
        return {str(status): int(count) for status, count in rows}

    def latest_task(self) -> SyncTask | None:
        return self.db.scalar(select(SyncTask).order_by(SyncTask.created_at.desc(), SyncTask.id.desc()).limit(1))

    def find_recent_task(
        self,
        *,
        task_type: str,
        source: str,
        market: str | None = None,
        statuses: list[str],
        created_after: datetime,
    ) -> SyncTask | None:
        """Find a recent task matching the given criteria.

        Used for idempotency checks — returns the most recent task that:
        - matches task_type, source, market
        - has one of the given statuses
        - was created after the given timestamp
        """
        stmt = (
            select(SyncTask)
            .where(
                SyncTask.task_type == task_type,
                SyncTask.source == source,
                SyncTask.status.in_(statuses),
                SyncTask.created_at >= created_after,
            )
            .order_by(SyncTask.created_at.desc(), SyncTask.id.desc())
            .limit(1)
        )
        if market:
            stmt = stmt.where(SyncTask.market == market)
        return self.db.scalar(stmt)

    def find_recent_raw_replay_task(
        self,
        *,
        raw_artifact_id: int,
        adjust_type: str,
        statuses: list[str],
        created_after: datetime,
    ) -> SyncTask | None:
        return self.db.scalar(
            select(SyncTask)
            .where(
                SyncTask.task_type == "daily_bars_raw_replay",
                SyncTask.input_raw_artifact_id == raw_artifact_id,
                SyncTask.adjust_type == adjust_type,
                SyncTask.status.in_(statuses),
                SyncTask.created_at >= created_after,
            )
            .order_by(SyncTask.created_at.desc(), SyncTask.id.desc())
            .limit(1)
        )

    def create_or_get_active_raw_replay_task(
        self,
        *,
        raw_artifact_id: int,
        adjust_type: str,
        market: str | None,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[SyncTask, bool]:
        task = SyncTask(
            task_type="daily_bars_raw_replay",
            source="replay",
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            input_raw_artifact_id=raw_artifact_id,
        )
        self.db.add(task)
        try:
            self.db.flush()
            return task, True
        except IntegrityError:
            self.db.rollback()
            existing_task = self.find_recent_raw_replay_task(
                raw_artifact_id=raw_artifact_id,
                adjust_type=adjust_type,
                statuses=["pending", "running"],
                created_after=datetime.min.replace(tzinfo=timezone.utc),
            )
            if existing_task is None:
                raise
            return existing_task, False
