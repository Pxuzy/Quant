from __future__ import annotations

import argparse
import json
from datetime import date

from apps.api.db.session import SessionLocal, configure_database, init_db
from apps.api.models import SyncTask
from apps.api.repositories.sync_tasks import SyncTaskRepository
from apps.api.services.market_data_sync_service import MarketDataSyncService
from apps.api.services.stock_sync_service import AUTO_SOURCE_CODE, StockSyncService
from apps.api.services.trading_calendar_service import TradingCalendarService

SUPPORTED_PENDING_TASK_TYPES = ("stock_list", "daily_bars", "daily_bars_market_repair", "calendars")


def configure_worker_database(database_url: str | None = None) -> None:
    if database_url:
        configure_database(database_url)
    init_db()


def enqueue_stock_sync(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    database_url: str | None = None,
) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return StockSyncService(db).create_stock_sync_task(source=source, market=market)
    finally:
        db.close()


def run_stock_sync_task(*, task_id: int, database_url: str | None = None) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return StockSyncService(db).run_stock_sync_task(task_id)
    finally:
        db.close()


def run_next_pending_stock_sync(*, database_url: str | None = None) -> SyncTask | None:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return StockSyncService(db).run_next_pending_stock_sync()
    finally:
        db.close()


def run_next_pending_sync(*, database_url: str | None = None) -> SyncTask | None:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        task = SyncTaskRepository(db).get_next_pending_any_task(SUPPORTED_PENDING_TASK_TYPES)
        if task is None:
            return None
        task_id = task.id
        task_type = task.task_type
    finally:
        db.close()

    if task_type == "stock_list":
        return run_stock_sync_task(task_id=task_id, database_url=database_url)
    if task_type == "daily_bars":
        return run_daily_bars_sync_task(task_id=task_id, database_url=database_url)
    if task_type == "daily_bars_market_repair":
        return run_market_daily_bars_repair_task(task_id=task_id, database_url=database_url)
    if task_type == "daily_bars_raw_replay":
        return run_raw_daily_bars_replay_task(task_id=task_id, database_url=database_url)
    if task_type == "calendars":
        return run_calendar_sync_task(task_id=task_id, database_url=database_url)
    raise ValueError(f"Unsupported pending sync task type: {task_type}")


def run_stock_sync(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    database_url: str | None = None,
) -> SyncTask:
    task = enqueue_stock_sync(source=source, market=market, database_url=database_url)
    return run_stock_sync_task(task_id=task.id, database_url=database_url)


def enqueue_daily_bars_sync(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    symbol: str,
    start_date: date,
    end_date: date,
    adjust_type: str = "none",
    database_url: str | None = None,
) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return MarketDataSyncService(db).create_daily_bars_sync_task(
            source=source,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
    finally:
        db.close()


def run_daily_bars_sync_task(*, task_id: int, database_url: str | None = None) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return MarketDataSyncService(db).run_daily_bars_sync_task(task_id)
    finally:
        db.close()


def run_next_pending_daily_bars_sync(*, database_url: str | None = None) -> SyncTask | None:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return MarketDataSyncService(db).run_next_pending_daily_bars_sync()
    finally:
        db.close()


def enqueue_market_daily_bars_repair(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    start_date: date,
    end_date: date,
    max_symbols: int = 20,
    start_policy: str = "requested_start",
    adjust_type: str = "none",
    database_url: str | None = None,
) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return MarketDataSyncService(db).create_market_daily_bars_repair_task(
            source=source,
            market=market,
            start_date=start_date,
            end_date=end_date,
            max_symbols=max_symbols,
            start_policy=start_policy,
            adjust_type=adjust_type,
        )
    finally:
        db.close()


def run_market_daily_bars_repair_task(*, task_id: int, database_url: str | None = None) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return MarketDataSyncService(db).run_market_daily_bars_repair_task(task_id)
    finally:
        db.close()


def run_next_pending_market_daily_bars_repair(*, database_url: str | None = None) -> SyncTask | None:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return MarketDataSyncService(db).run_next_pending_market_daily_bars_repair()
    finally:
        db.close()


def run_market_daily_bars_repair(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    start_date: date,
    end_date: date,
    max_symbols: int = 20,
    start_policy: str = "requested_start",
    adjust_type: str = "none",
    database_url: str | None = None,
) -> SyncTask:
    task = enqueue_market_daily_bars_repair(
        source=source,
        market=market,
        start_date=start_date,
        end_date=end_date,
        max_symbols=max_symbols,
        start_policy=start_policy,
        adjust_type=adjust_type,
        database_url=database_url,
    )
    return run_market_daily_bars_repair_task(task_id=task.id, database_url=database_url)


def run_daily_bars_sync(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    symbol: str,
    start_date: date,
    end_date: date,
    adjust_type: str = "none",
    database_url: str | None = None,
) -> SyncTask:
    task = enqueue_daily_bars_sync(
        source=source,
        market=market,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        database_url=database_url,
    )
    return run_daily_bars_sync_task(task_id=task.id, database_url=database_url)


def enqueue_calendar_sync(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    start_date: date,
    end_date: date,
    database_url: str | None = None,
) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return TradingCalendarService(db).create_calendar_sync_task(
            source=source,
            market=market,
            start_date=start_date,
            end_date=end_date,
        )
    finally:
        db.close()


def run_calendar_sync_task(*, task_id: int, database_url: str | None = None) -> SyncTask:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return TradingCalendarService(db).run_calendar_sync_task(task_id)
    finally:
        db.close()


def run_next_pending_calendar_sync(*, database_url: str | None = None) -> SyncTask | None:
    configure_worker_database(database_url)
    db = SessionLocal()
    try:
        return TradingCalendarService(db).run_next_pending_calendar_sync()
    finally:
        db.close()


def run_calendar_sync(
    *,
    source: str = AUTO_SOURCE_CODE,
    market: str = "A_SHARE",
    start_date: date,
    end_date: date,
    database_url: str | None = None,
) -> SyncTask:
    task = enqueue_calendar_sync(
        source=source,
        market=market,
        start_date=start_date,
        end_date=end_date,
        database_url=database_url,
    )
    return run_calendar_sync_task(task_id=task.id, database_url=database_url)


def task_to_payload(task: SyncTask | None) -> dict:
    if task is None:
        return {"status": "idle", "message": "No pending sync task found."}
    return {
        "id": task.id,
        "task_type": task.task_type,
        "source": task.source,
        "market": task.market,
        "status": task.status,
        "records_read": task.records_read,
        "records_written": task.records_written,
        "error_message": task.error_message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a stock data sync task.")
    parser.add_argument(
        "--task-type",
        choices=["stock_list", "daily_bars", "daily_bars_market_repair", "calendars"],
        default=None,
    )
    parser.add_argument("--source", default=AUTO_SOURCE_CODE)
    parser.add_argument("--market", default="A_SHARE")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--max-symbols", type=int, default=20)
    parser.add_argument("--start-policy", choices=["requested_start", "listing_date"], default="requested_start")
    parser.add_argument("--adjust-type", choices=["none", "qfq", "hfq"], default="none")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--task-id", type=int, default=None, help="Execute an existing pending stock sync task.")
    parser.add_argument("--enqueue", action="store_true", help="Create a pending stock sync task and exit.")
    parser.add_argument("--run-next-pending", action="store_true", help="Execute the oldest pending stock sync task.")
    args = parser.parse_args(argv)
    task_type = args.task_type or "stock_list"

    if args.run_next_pending and args.task_type is None:
        task = run_next_pending_sync(database_url=args.database_url)
    elif task_type == "daily_bars":
        if args.task_id is not None:
            task = run_daily_bars_sync_task(task_id=args.task_id, database_url=args.database_url)
        elif args.run_next_pending:
            task = run_next_pending_daily_bars_sync(database_url=args.database_url)
        else:
            if args.symbol is None or args.start_date is None or args.end_date is None:
                parser.error("--symbol, --start-date, and --end-date are required for daily_bars tasks.")
            start_date = date.fromisoformat(args.start_date)
            end_date = date.fromisoformat(args.end_date)
            if args.enqueue:
                task = enqueue_daily_bars_sync(
                    source=args.source,
                    market=args.market,
                    symbol=args.symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust_type=args.adjust_type,
                    database_url=args.database_url,
                )
            else:
                task = run_daily_bars_sync(
                    source=args.source,
                    market=args.market,
                    symbol=args.symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust_type=args.adjust_type,
                    database_url=args.database_url,
                )
    elif task_type == "daily_bars_market_repair":
        if args.task_id is not None:
            task = run_market_daily_bars_repair_task(task_id=args.task_id, database_url=args.database_url)
        elif args.run_next_pending:
            task = run_next_pending_market_daily_bars_repair(database_url=args.database_url)
        else:
            if args.start_date is None or args.end_date is None:
                parser.error("--start-date and --end-date are required for daily_bars_market_repair tasks.")
            start_date = date.fromisoformat(args.start_date)
            end_date = date.fromisoformat(args.end_date)
            if args.enqueue:
                task = enqueue_market_daily_bars_repair(
                    source=args.source,
                    market=args.market,
                    start_date=start_date,
                    end_date=end_date,
                    max_symbols=args.max_symbols,
                    start_policy=args.start_policy,
                    adjust_type=args.adjust_type,
                    database_url=args.database_url,
                )
            else:
                task = run_market_daily_bars_repair(
                    source=args.source,
                    market=args.market,
                    start_date=start_date,
                    end_date=end_date,
                    max_symbols=args.max_symbols,
                    start_policy=args.start_policy,
                    adjust_type=args.adjust_type,
                    database_url=args.database_url,
                )
    elif task_type == "calendars":
        if args.task_id is not None:
            task = run_calendar_sync_task(task_id=args.task_id, database_url=args.database_url)
        elif args.run_next_pending:
            task = run_next_pending_calendar_sync(database_url=args.database_url)
        else:
            if args.start_date is None or args.end_date is None:
                parser.error("--start-date and --end-date are required for calendars tasks.")
            start_date = date.fromisoformat(args.start_date)
            end_date = date.fromisoformat(args.end_date)
            if args.enqueue:
                task = enqueue_calendar_sync(
                    source=args.source,
                    market=args.market,
                    start_date=start_date,
                    end_date=end_date,
                    database_url=args.database_url,
                )
            else:
                task = run_calendar_sync(
                    source=args.source,
                    market=args.market,
                    start_date=start_date,
                    end_date=end_date,
                    database_url=args.database_url,
                )
    elif args.enqueue:
        task = enqueue_stock_sync(source=args.source, market=args.market, database_url=args.database_url)
    elif args.task_id is not None:
        task = run_stock_sync_task(task_id=args.task_id, database_url=args.database_url)
    elif args.run_next_pending:
        task = run_next_pending_stock_sync(database_url=args.database_url)
    else:
        task = run_stock_sync(source=args.source, market=args.market, database_url=args.database_url)

    print(json.dumps(task_to_payload(task), ensure_ascii=True))
    return 0 if task is None or task.status == "success" or (args.enqueue and task.status == "pending") else 1


if __name__ == "__main__":
    raise SystemExit(main())
