from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import ceil

from sqlalchemy.orm import Session

from backend.app.models import SyncSchedule, SyncTask
from backend.app.repositories.ingest_batches import IngestBatchRepository
from backend.app.repositories.sync_schedules import SyncScheduleRepository
from backend.app.repositories.sync_tasks import SyncTaskRepository
from backend.app.services.stock_sync_service import StockSyncService
from backend.app.services.sync_service import MarketDataSyncService
from backend.app.services.trading_calendar_service import TradingCalendarService

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


CRON_FIELD_RANGES: tuple[tuple[int, int], ...] = (
    (0, 59),
    (0, 23),
    (1, 31),
    (1, 12),
    (0, 7),
)
DAILY_BARS_DEFAULT_WINDOW_DAYS = 180


class SyncScheduleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.schedule_repo = SyncScheduleRepository(db)
        self.task_repo = SyncTaskRepository(db)

    def list_schedules(self) -> dict:
        self.schedule_repo.ensure_defaults()
        self.db.commit()
        schedules = self.schedule_repo.list_all()
        return {"items": schedules, "total": len(schedules)}

    def update_schedule(self, code: str, *, enabled: bool | None = None, cron_expression: str | None = None, source: str | None = None, market: str | None = None, symbol: str | None = None) -> SyncSchedule | None:
        if cron_expression is not None:
            _validate_cron_expression(cron_expression)
        self.schedule_repo.ensure_defaults()
        schedule = self.schedule_repo.update_schedule(code, enabled=enabled, cron_expression=cron_expression, source=source, market=market, symbol=symbol)
        if schedule is None:
            self.db.rollback()
            return None
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def trigger_schedule(self, code: str) -> SyncTask | None:
        self.schedule_repo.ensure_defaults()
        schedule = self.schedule_repo.get_by_code(code)
        if schedule is None:
            self.db.rollback()
            return None
        task = self._create_task_from_schedule(schedule)
        triggered_at = datetime.now(timezone.utc)
        schedule.last_triggered_at = triggered_at
        self.task_repo.add_log(task, level="info", message="Sync schedule triggered.", payload={
            "schedule_code": schedule.code, "schedule_name": schedule.name,
            "cron_expression": schedule.cron_expression, "task_type": schedule.task_type,
            "source": schedule.source, "market": schedule.market, "symbol": schedule.symbol,
            "task_id": task.id, "triggered_at": triggered_at.isoformat(),
        })
        self.db.commit()
        self.db.refresh(task)
        return task

    def _create_task_from_schedule(self, schedule: SyncSchedule) -> SyncTask:
        market = schedule.market or "A_SHARE"
        if schedule.task_type == "stock_list":
            return StockSyncService(self.db).create_stock_sync_task(source=schedule.source, market=market)
        if schedule.task_type == "daily_bars":
            if not schedule.symbol:
                self.db.rollback()
                raise ValueError("请先为日线定时规则配置股票代码，第一阶段暂不支持全市场日线批量触发。")
            start_date, end_date = self._default_daily_bars_window()
            return MarketDataSyncService(self.db).create_daily_bars_sync_task(source=schedule.source, market=market, symbol=schedule.symbol, start_date=start_date, end_date=end_date)
        if schedule.task_type == "calendars":
            start_date, end_date = self._default_calendar_window()
            return TradingCalendarService(self.db).create_calendar_sync_task(source=schedule.source, market=market, start_date=start_date, end_date=end_date)
        self.db.rollback()
        raise ValueError(f"Unsupported sync schedule task_type '{schedule.task_type}'.")

    @staticmethod
    def _default_daily_bars_window() -> tuple[date, date]:
        end_date = datetime.now(timezone.utc).date()
        return end_date - timedelta(days=DAILY_BARS_DEFAULT_WINDOW_DAYS), end_date

    @staticmethod
    def _default_calendar_window() -> tuple[date, date]:
        today = datetime.now(timezone.utc).date()
        return today - timedelta(days=365), today + timedelta(days=90)


def _validate_cron_expression(expression: str) -> None:
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError("cron expression must contain exactly 5 fields.")
    for field, (min_value, max_value) in zip(fields, CRON_FIELD_RANGES, strict=True):
        _validate_cron_field(field, min_value=min_value, max_value=max_value)


def _validate_cron_field(field: str, *, min_value: int, max_value: int) -> None:
    if not field:
        raise ValueError("cron expression contains an empty field.")
    for item in field.split(","):
        if not item:
            raise ValueError("cron expression contains an empty list item.")
        base, step = _split_cron_step(item)
        if step is not None and step <= 0:
            raise ValueError("cron step must be greater than 0.")
        if base == "*":
            continue
        if "-" in base:
            start_text, end_text = base.split("-", 1)
            start = _parse_cron_int(start_text, min_value=min_value, max_value=max_value)
            end = _parse_cron_int(end_text, min_value=min_value, max_value=max_value)
            if start > end:
                raise ValueError("cron range start must be before or equal to range end.")
            continue
        _parse_cron_int(base, min_value=min_value, max_value=max_value)


def _split_cron_step(item: str) -> tuple[str, int | None]:
    if "/" not in item:
        return item, None
    base, step_text = item.split("/", 1)
    if not base or not step_text:
        raise ValueError("cron step must include both base and step.")
    return base, _parse_cron_int(step_text, min_value=1, max_value=999)


def _parse_cron_int(value: str, *, min_value: int, max_value: int) -> int:
    if not value.isdigit():
        raise ValueError("cron expression contains a non-numeric value.")
    number = int(value)
    if number < min_value or number > max_value:
        raise ValueError(f"cron value {number} is outside {min_value}-{max_value}.")
    return number
