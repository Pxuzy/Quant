from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from sqlalchemy import func, select

from apps.api.core.config import reset_settings_cache
from apps.api.db.session import SessionLocal, configure_database, init_db
from apps.api.models import Dataset, Stock, SyncTask, TradingCalendar
from apps.api.repositories.sync_tasks import SyncTaskRepository
from apps.worker.sync_stocks import (
    enqueue_calendar_sync,
    enqueue_market_daily_bars_repair,
    enqueue_stock_sync,
    main,
    run_next_pending_calendar_sync,
    run_next_pending_stock_sync,
    run_stock_sync,
)


def install_fake_akshare(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(
            stock_info_a_code_name=lambda: [
                {"code": "600519", "name": "Kweichow Moutai", "listing_date": "2001-08-27"},
                {"code": "000001", "name": "Ping An Bank", "listing_date": "1991-04-03"},
                {"code": "601318", "name": "Ping An Insurance", "listing_date": "2007-03-01"},
                {"code": "300750", "name": "CATL", "listing_date": "2018-06-11"},
                {"code": "688981", "name": "SMIC", "listing_date": "2020-07-16"},
                {"code": "430047", "name": "NQ Technology", "listing_date": "2014-01-24"},
                {"code": "000002", "name": "Vanke A", "listing_date": "1991-01-29"},
                {"code": "600001", "name": "Legacy Industrial", "listing_date": "1990-12-19"},
            ]
        ),
    )


class FakeBaoStockLoginResult:
    error_code = "0"
    error_msg = ""


class FakeBaoStockCalendarResultSet:
    fields = ["calendar_date", "is_trading_day"]

    def __init__(self) -> None:
        self._rows = [["2026-06-01", "1"], ["2026-06-02", "1"], ["2026-06-06", "0"]]
        self._index = -1
        self.error_code = "0"
        self.error_msg = ""

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


class FakeBaoStockDailyResultSet:
    fields = ["date", "code", "open", "high", "low", "close", "preclose", "volume", "amount", "adjustflag"]

    def __init__(self, code: str) -> None:
        self._rows = [
            ["2026-06-01", code, "10.00", "11.00", "9.50", "10.50", "10.00", "1000", "10500", "3"],
            ["2026-06-02", code, "10.50", "12.00", "10.20", "11.20", "10.50", "1200", "13440", "3"],
        ]
        self._index = -1
        self.error_code = "0"
        self.error_msg = ""

    def next(self):
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self):
        return self._rows[self._index]


def install_fake_baostock(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "baostock",
        SimpleNamespace(
            login=lambda: FakeBaoStockLoginResult(),
            logout=lambda: None,
            query_stock_basic=lambda: None,
            query_trade_dates=lambda **kwargs: FakeBaoStockCalendarResultSet(),
            query_history_k_data_plus=lambda code, fields, **kwargs: FakeBaoStockDailyResultSet(code),
        ),
    )


def test_worker_claims_pending_stock_sync_task(tmp_path, monkeypatch):
    install_fake_akshare(monkeypatch)
    database_url = f"sqlite:///{tmp_path / 'worker-test.db'}"
    pending_task = enqueue_stock_sync(database_url=database_url)

    assert pending_task.status == "pending"
    assert pending_task.records_written == 0

    task = run_next_pending_stock_sync(database_url=database_url)

    assert task is not None
    assert task.id == pending_task.id
    assert task.status == "success"
    assert task.records_written >= 8

    db = SessionLocal()
    try:
        stock_count = db.scalar(select(func.count(Stock.id)))
        dataset = db.scalar(select(Dataset).where(Dataset.name == "stocks"))
    finally:
        db.close()

    assert stock_count >= 8
    assert dataset is not None
    assert dataset.storage_type == "postgres"
    assert dataset.layer == "silver"


def test_worker_claim_commit_is_visible_to_other_sessions(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'worker-claim-visible.db'}"
    configure_database(database_url)
    init_db(drop_all=True)
    db = SessionLocal()
    try:
        task = SyncTask(task_type="stock_list", source="auto", market="A_SHARE", status="pending")
        db.add(task)
        db.commit()
        task_id = task.id

        SyncTaskRepository(db).mark_running(task)

        other_db = SessionLocal()
        try:
            visible_task = other_db.get(SyncTask, task_id)
            assert visible_task is not None
            assert visible_task.status == "running"
            assert visible_task.started_at is not None
            logs = SyncTaskRepository(other_db).list_task_logs(task_id)
        finally:
            other_db.close()
    finally:
        db.close()

    assert any(log.message == "Sync task claimed by lightweight worker." for log in logs)


def test_worker_run_stock_sync_smoke_helper_uses_sqlite_fallback(tmp_path, monkeypatch):
    install_fake_akshare(monkeypatch)
    task = run_stock_sync(database_url=f"sqlite:///{tmp_path / 'worker-smoke.db'}")

    assert task.status == "success"
    assert task.records_written >= 8


def test_worker_cli_runs_source_sync_by_default(tmp_path, capsys, monkeypatch):
    install_fake_akshare(monkeypatch)
    exit_code = main(
        [
            "--database-url",
            f"sqlite:///{tmp_path / 'worker-cli.db'}",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"source": "auto"' in captured.out
    assert '"status": "success"' in captured.out


def test_worker_cli_run_next_pending_claims_market_repair_without_task_type(tmp_path, capsys, monkeypatch):
    install_fake_baostock(monkeypatch)
    monkeypatch.setenv("DATA_LAKE_DIR", str(tmp_path / "lake"))
    reset_settings_cache()
    database_url = f"sqlite:///{tmp_path / 'worker-market-repair.db'}"

    configure_database(database_url)
    init_db(drop_all=True)
    db = SessionLocal()
    try:
        db.add(
            Stock(
                symbol="600519",
                exchange="SSE",
                market="A_SHARE",
                name="贵州茅台",
                status="LISTED",
                industry="白酒",
                source="fixture",
            )
        )
        db.add_all(
            [
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 1), is_open=True, source="fixture"),
                TradingCalendar(market="A_SHARE", trade_date=date(2026, 6, 2), is_open=True, source="fixture"),
            ]
        )
        db.commit()
    finally:
        db.close()

    pending_task = enqueue_market_daily_bars_repair(
        source="baostock",
        database_url=database_url,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 2),
        max_symbols=1,
    )

    exit_code = main(
        [
            "--database-url",
            database_url,
            "--run-next-pending",
        ]
    )

    captured = capsys.readouterr()
    db = SessionLocal()
    try:
        task = db.get(SyncTask, pending_task.id)
        dataset = db.scalar(select(Dataset).where(Dataset.name == "daily_bars"))
    finally:
        db.close()
        reset_settings_cache()

    assert exit_code == 0
    assert '"task_type": "daily_bars_market_repair"' in captured.out
    assert '"status": "success"' in captured.out
    assert task is not None
    assert task.status == "success"
    assert task.records_written == 2
    assert dataset is not None
    assert dataset.storage_type == "parquet"


def test_worker_cli_run_next_pending_keeps_explicit_stock_list_mode(tmp_path, capsys, monkeypatch):
    install_fake_akshare(monkeypatch)
    database_url = f"sqlite:///{tmp_path / 'worker-explicit-stock-list.db'}"
    pending_task = enqueue_stock_sync(database_url=database_url)

    exit_code = main(
        [
            "--database-url",
            database_url,
            "--task-type",
            "stock_list",
            "--run-next-pending",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert f'"id": {pending_task.id}' in captured.out
    assert '"task_type": "stock_list"' in captured.out
    assert '"status": "success"' in captured.out


def test_worker_claims_pending_calendar_sync_task(tmp_path, monkeypatch):
    install_fake_baostock(monkeypatch)
    database_url = f"sqlite:///{tmp_path / 'worker-calendar.db'}"
    pending_task = enqueue_calendar_sync(
        database_url=database_url,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 6),
    )

    assert pending_task.status == "pending"

    task = run_next_pending_calendar_sync(database_url=database_url)

    assert task is not None
    assert task.id == pending_task.id
    assert task.status == "success"
    assert task.records_written == 3

    db = SessionLocal()
    try:
        calendar_count = db.scalar(select(func.count(TradingCalendar.id)))
        dataset = db.scalar(select(Dataset).where(Dataset.name == "trading_calendars"))
    finally:
        db.close()

    assert calendar_count == 3
    assert dataset is not None
    assert dataset.storage_type == "postgres"
