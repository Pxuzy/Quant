from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import SyncSchedule

DEFAULT_SYNC_SCHEDULES: tuple[dict[str, str | bool | None], ...] = (
    {
        "code": "daily_bars_after_close",
        "name": "每天收盘后更新日线",
        "task_type": "daily_bars",
        "source": "auto",
        "market": "A_SHARE",
        "symbol": None,
        "cron_expression": "30 18 * * 1-5",
        "enabled": False,
        "schedule_note": "A 股收盘后按数据源优先级自动更新日线；第一版仅管理配置，不启动真实 cron 执行器。",
    },
    {
        "code": "weekly_stock_pool",
        "name": "每周更新股票池",
        "task_type": "stock_list",
        "source": "auto",
        "market": "A_SHARE",
        "symbol": None,
        "cron_expression": "0 10 * * 6",
        "enabled": False,
        "schedule_note": "周末校验上市状态、行业和新增股票，保持 A 股股票池可用。",
    },
    {
        "code": "monthly_calendar_backfill",
        "name": "每月补齐交易日历",
        "task_type": "calendars",
        "source": "auto",
        "market": "A_SHARE",
        "symbol": None,
        "cron_expression": "0 9 1 * *",
        "enabled": False,
        "schedule_note": "定期补齐交易日历覆盖范围，为日线缺口检查和增量同步提供基准。",
    },
)

DEFAULT_SCHEDULE_ORDER = {str(item["code"]): index for index, item in enumerate(DEFAULT_SYNC_SCHEDULES)}


class SyncScheduleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_defaults(self) -> list[SyncSchedule]:
        schedules: list[SyncSchedule] = []
        for payload in DEFAULT_SYNC_SCHEDULES:
            code = str(payload["code"])
            schedule = self.get_by_code(code)
            if schedule is None:
                schedule = SyncSchedule(**payload)
                self.db.add(schedule)
            else:
                schedule.name = str(payload["name"])
                schedule.task_type = str(payload["task_type"])
                schedule.schedule_note = str(payload["schedule_note"])
            schedules.append(schedule)
        self.db.flush()
        return schedules

    def list_all(self) -> list[SyncSchedule]:
        schedules = list(self.db.scalars(select(SyncSchedule).order_by(SyncSchedule.code.asc())).all())
        return sorted(schedules, key=lambda item: (DEFAULT_SCHEDULE_ORDER.get(item.code, 999), item.code))

    def get_by_code(self, code: str) -> SyncSchedule | None:
        return self.db.scalar(select(SyncSchedule).where(SyncSchedule.code == code))

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
        schedule = self.get_by_code(code)
        if schedule is None:
            return None
        if enabled is not None:
            schedule.enabled = enabled
        if cron_expression is not None:
            schedule.cron_expression = cron_expression
        if source is not None:
            schedule.source = source
        if market is not None:
            schedule.market = market
        if symbol is not None:
            schedule.symbol = symbol or None
        self.db.flush()
        return schedule
