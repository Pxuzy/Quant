from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.models import SyncSchedule, SyncTask
from backend.app.repositories.sync_schedules import SyncScheduleRepository
from backend.app.repositories.sync_tasks import SyncTaskRepository
from backend.app.services.stock_sync_service import StockSyncService
from backend.app.services.sync_service import MarketDataSyncService
from backend.app.services.trading_calendar_service import TradingCalendarService

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

    def update_schedule(
        self,
        code: str,
        *,
        enabled: bool | None = None,
        cron_expression: str | None = None,
        source: str | None = None,
        market: str | None = None,
        symbol: str | None = None,
    ) -> SyncSchedule | None:
        if cron_expression is not None:
            _validate_cron_expression(cron_expression)
        self.schedule_repo.ensure_defaults()
        schedule = self.schedule_repo.update_schedule(
            code,
            enabled=enabled,
            cron_expression=cron_expression,
            source=source,
            market=market,
            symbol=symbol,
        )
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
        self.task_repo.add_log(
            task,
            level="info",
            message="Sync schedule triggered.",
            payload={
                "schedule_code": schedule.code,
                "schedule_name": schedule.name,
                "cron_expression": schedule.cron_expression,
                "task_type": schedule.task_type,
                "source": schedule.source,
                "market": schedule.market,
                "symbol": schedule.symbol,
                "task_id": task.id,
                "triggered_at": triggered_at.isoformat(),
            },
        )
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
            return MarketDataSyncService(self.db).create_daily_bars_sync_task(
                source=schedule.source,
                market=market,
                symbol=schedule.symbol,
                start_date=start_date,
                end_date=end_date,
            )

        if schedule.task_type == "calendars":
            start_date, end_date = self._default_calendar_window()
            return TradingCalendarService(self.db).create_calendar_sync_task(
                source=schedule.source,
                market=market,
                start_date=start_date,
                end_date=end_date,
            )

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
