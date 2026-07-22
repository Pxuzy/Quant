from __future__ import annotations

from datetime import date
from math import ceil

from sqlalchemy.orm import Session

from backend.app.repositories.ingest_batches import IngestBatchRepository
from backend.app.repositories.sync_schedules import SyncScheduleRepository
from backend.app.repositories.sync_tasks import SyncTaskRepository

WORKER_COMMAND = "python -m backend.worker.sync_stocks --run-next-pending"
WORKER_NOTE = "创建同步任务后，API 只负责入队；本地轻量 worker 会执行最早的待执行 V1 同步任务。"
SUPPORTED_WORKER_TASK_TYPES = ("stock_list", "daily_bars", "daily_bars_market_repair", "calendars", "daily_bars_raw_replay")


def _task_ref(task) -> dict[str, object | None]:
    return {
        "id": task.id if task else None,
        "task_type": task.task_type if task else None,
        "status": task.status if task else None,
        "created_at": task.created_at if task else None,
        "started_at": task.started_at if task else None,
        "finished_at": task.finished_at if task else None,
    }


class SyncTaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.task_repo = SyncTaskRepository(db)
        self.ingest_batch_repo = IngestBatchRepository(db)
        self.schedule_repo = SyncScheduleRepository(db)

    def get_task(self, task_id: int):
        return self.task_repo.get_task(task_id)

    def get_task_logs(self, task_id: int) -> dict | None:
        task = self.task_repo.get_task(task_id)
        if task is None:
            return None

        logs = self.task_repo.list_task_logs(task_id)
        return {"task_id": task.id, "items": logs, "total": len(logs)}

    def get_task_ingest_batches(self, task_id: int) -> dict | None:
        task = self.task_repo.get_task(task_id)
        if task is None:
            return None

        batches = self.ingest_batch_repo.list_for_task(task_id)
        return {"task_id": task.id, "items": batches, "total": len(batches)}

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
    ) -> dict:
        items, total = self.task_repo.list_tasks(
            status=status,
            source=source,
            task_type=task_type,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
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

    def get_runner_status(self) -> dict:
        self.schedule_repo.ensure_defaults()
        self.db.commit()
        schedules = self.schedule_repo.list_all()
        counts = self.task_repo.count_by_status()
        latest_task = self.task_repo.latest_task()
        current_task = self.task_repo.current_running_task()
        next_pending_task = self.task_repo.get_next_pending_any_task(SUPPORTED_WORKER_TASK_TYPES)
        latest_success_task = self.task_repo.latest_task_by_status("success")
        latest_failed_task = self.task_repo.latest_task_by_status("failed")
        latest_triggered_at = max(
            (schedule.last_triggered_at for schedule in schedules if schedule.last_triggered_at is not None),
            default=None,
        )
        latest_worker_activity_at = max(
            (
                timestamp
                for timestamp in [
                    current_task.started_at if current_task else None,
                    latest_success_task.finished_at if latest_success_task else None,
                    latest_failed_task.finished_at if latest_failed_task else None,
                ]
                if timestamp is not None
            ),
            default=None,
        )
        pending_count = counts.get("pending", 0)
        running_count = counts.get("running", 0)
        failed_count = counts.get("failed", 0)
        partial_success_count = counts.get("partial_success", 0)
        enabled_schedules = sum(1 for schedule in schedules if schedule.enabled)

        if running_count:
            status = "running"
            message = "已有任务正在运行，页面会自动刷新同步记录。"
        elif pending_count:
            status = "pending"
            message = "有任务等待 worker 执行；请确认本地 worker 进程已启动。"
        elif failed_count or partial_success_count:
            status = "warning"
            message = "最近存在失败或部分成功任务，请打开同步记录查看失败项和批次错误。"
        else:
            status = "idle"
            message = "当前没有等待或运行中的任务。"

        if enabled_schedules:
            message = f"{message} 定时规则已启用，但当前第一版仍以轻量 worker/手动触发为主。"

        return {
            "mode": "lightweight_worker",
            "status": status,
            "message": message,
            "worker_command": WORKER_COMMAND,
            "worker_note": WORKER_NOTE,
            "supported_task_types": list(SUPPORTED_WORKER_TASK_TYPES),
            "pending_count": pending_count,
            "running_count": running_count,
            "failed_count": failed_count,
            "partial_success_count": partial_success_count,
            "success_count": counts.get("success", 0),
            "enabled_schedules": enabled_schedules,
            "total_schedules": len(schedules),
            "latest_task_id": latest_task.id if latest_task else None,
            "latest_task_status": latest_task.status if latest_task else None,
            "latest_task_created_at": latest_task.created_at if latest_task else None,
            "latest_triggered_at": latest_triggered_at,
            "current_task": _task_ref(current_task),
            "next_pending_task": _task_ref(next_pending_task),
            "latest_success_task": _task_ref(latest_success_task),
            "latest_failed_task": _task_ref(latest_failed_task),
            "latest_worker_activity_at": latest_worker_activity_at,
        }
