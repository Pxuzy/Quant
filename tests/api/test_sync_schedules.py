from __future__ import annotations

from datetime import date
from datetime import datetime, timezone

from backend.app.db.session import SessionLocal
from backend.app.models import SyncTask


def test_sync_schedules_api_returns_default_rules(client):
    response = client.get("/api/sync-tasks/schedules")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3

    schedules = {item["code"]: item for item in payload["items"]}
    assert set(schedules) == {
        "daily_bars_after_close",
        "weekly_stock_pool",
        "monthly_calendar_backfill",
    }

    daily_bars = schedules["daily_bars_after_close"]
    assert daily_bars["name"] == "每天收盘后更新日线"
    assert daily_bars["task_type"] == "daily_bars"
    assert daily_bars["source"] == "auto"
    assert daily_bars["market"] == "A_SHARE"
    assert daily_bars["enabled"] is False
    assert daily_bars["cron_expression"] == "30 18 * * 1-5"
    assert "收盘" in daily_bars["schedule_note"]


def test_sync_runner_status_reports_queue_and_schedule_state(client, fake_akshare):
    idle_response = client.get("/api/sync-tasks/runner-status")

    assert idle_response.status_code == 200
    idle_payload = idle_response.json()
    assert idle_payload["mode"] == "lightweight_worker"
    assert idle_payload["status"] == "idle"
    assert idle_payload["pending_count"] == 0
    assert idle_payload["running_count"] == 0
    assert idle_payload["total_schedules"] == 3
    assert "backend.worker.sync_stocks" in idle_payload["worker_command"]
    assert "--run-next-pending" in idle_payload["worker_command"]
    assert "待执行" in idle_payload["worker_note"]
    assert "daily_bars_market_repair" in idle_payload["supported_task_types"]
    assert idle_payload["current_task"]["id"] is None
    assert idle_payload["next_pending_task"]["id"] is None
    assert idle_payload["latest_success_task"]["id"] is None
    assert idle_payload["latest_failed_task"]["id"] is None
    assert idle_payload["latest_worker_activity_at"] is None

    task_response = client.post("/api/stocks/sync", json={"source": "auto", "market": "A_SHARE"})
    assert task_response.status_code == 201

    pending_response = client.get("/api/sync-tasks/runner-status")
    assert pending_response.status_code == 200
    pending_payload = pending_response.json()
    assert pending_payload["status"] == "pending"
    assert pending_payload["pending_count"] == 1
    assert pending_payload["latest_task_id"] == task_response.json()["id"]
    assert pending_payload["next_pending_task"]["id"] == task_response.json()["id"]
    assert pending_payload["next_pending_task"]["task_type"] == "stock_list"
    assert "worker" in pending_payload["message"]
    assert pending_payload["worker_command"] == idle_payload["worker_command"]


def test_sync_runner_status_reports_worker_execution_refs(client):
    started_at = datetime(2026, 6, 9, 18, 30, tzinfo=timezone.utc)
    success_finished_at = datetime(2026, 6, 9, 18, 35, tzinfo=timezone.utc)
    failed_finished_at = datetime(2026, 6, 9, 18, 40, tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        running_task = SyncTask(
            task_type="daily_bars_market_repair",
            source="auto",
            market="A_SHARE",
            status="running",
            started_at=started_at,
            progress=35,
        )
        success_task = SyncTask(
            task_type="daily_bars",
            source="baostock",
            market="A_SHARE",
            symbol="600519",
            status="success",
            started_at=started_at,
            finished_at=success_finished_at,
            records_written=3,
        )
        failed_task = SyncTask(
            task_type="calendars",
            source="tushare",
            market="A_SHARE",
            status="failed",
            started_at=started_at,
            finished_at=failed_finished_at,
            error_message="calendar failed",
        )
        pending_task = SyncTask(
            task_type="stock_list",
            source="akshare",
            market="A_SHARE",
            status="pending",
        )
        db.add_all([success_task, failed_task, running_task, pending_task])
        db.commit()
        expected_running_id = running_task.id
        expected_success_id = success_task.id
        expected_failed_id = failed_task.id
        expected_pending_id = pending_task.id
    finally:
        db.close()

    response = client.get("/api/sync-tasks/runner-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["current_task"]["id"] == expected_running_id
    assert payload["current_task"]["task_type"] == "daily_bars_market_repair"
    assert payload["next_pending_task"]["id"] == expected_pending_id
    assert payload["latest_success_task"]["id"] == expected_success_id
    assert payload["latest_failed_task"]["id"] == expected_failed_id
    assert payload["latest_worker_activity_at"].startswith("2026-06-09T18:40:00")


def test_sync_tasks_api_filters_by_task_scope(client):
    db = SessionLocal()
    try:
        db.add_all(
            [
                SyncTask(
                    task_type="daily_bars",
                    source="baostock",
                    market="A_SHARE",
                    symbol="600519",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 5),
                    status="success",
                ),
                SyncTask(
                    task_type="daily_bars",
                    source="akshare",
                    market="A_SHARE",
                    symbol="000001",
                    start_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 5),
                    status="success",
                ),
                SyncTask(
                    task_type="stock_list",
                    source="baostock",
                    market="A_SHARE",
                    status="success",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/sync-tasks",
        params={
            "status": "success",
            "source": "baostock",
            "task_type": "daily_bars",
            "market": "A_SHARE",
            "symbol": "600519",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["task_type"] == "daily_bars"
    assert payload["items"][0]["source"] == "baostock"
    assert payload["items"][0]["symbol"] == "600519"


def test_sync_schedule_update_toggles_enabled_and_updates_cron(client):
    response = client.patch(
        "/api/sync-tasks/schedules/daily_bars_after_close",
        json={"enabled": True, "cron_expression": "0 19 * * 1-5"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "daily_bars_after_close"
    assert payload["enabled"] is True
    assert payload["cron_expression"] == "0 19 * * 1-5"

    list_response = client.get("/api/sync-tasks/schedules")
    schedules = {item["code"]: item for item in list_response.json()["items"]}
    assert schedules["daily_bars_after_close"]["enabled"] is True
    assert schedules["daily_bars_after_close"]["cron_expression"] == "0 19 * * 1-5"


def test_sync_schedule_update_accepts_step_cron_expression(client):
    response = client.patch(
        "/api/sync-tasks/schedules/monthly_calendar_backfill",
        json={"cron_expression": "*/15 9-18 * * 1-5"},
    )

    assert response.status_code == 200
    assert response.json()["cron_expression"] == "*/15 9-18 * * 1-5"


def test_sync_schedule_update_rejects_invalid_cron_expression(client):
    response = client.patch(
        "/api/sync-tasks/schedules/daily_bars_after_close",
        json={"cron_expression": "not a cron"},
    )

    assert response.status_code == 400
    assert "cron" in response.json()["detail"].lower()


def test_sync_schedule_update_changes_source_and_symbol_scope(client):
    response = client.patch(
        "/api/sync-tasks/schedules/daily_bars_after_close",
        json={"source": "baostock", "market": "A_SHARE", "symbol": "600519"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "baostock"
    assert payload["market"] == "A_SHARE"
    assert payload["symbol"] == "600519"

    clear_response = client.patch(
        "/api/sync-tasks/schedules/daily_bars_after_close",
        json={"symbol": ""},
    )

    assert clear_response.status_code == 200
    assert clear_response.json()["symbol"] is None


def test_sync_schedule_trigger_creates_task_and_updates_last_triggered_at(client, fake_akshare):
    response = client.post("/api/sync-tasks/schedules/weekly_stock_pool/trigger")

    assert response.status_code == 201
    task = response.json()
    assert task["task_type"] == "stock_list"
    assert task["source"] == "auto"
    assert task["market"] == "A_SHARE"
    assert task["status"] == "pending"

    schedules_response = client.get("/api/sync-tasks/schedules")
    schedules = {item["code"]: item for item in schedules_response.json()["items"]}
    assert schedules["weekly_stock_pool"]["last_triggered_at"] is not None

    logs_response = client.get(f"/api/sync-tasks/{task['id']}/logs")
    assert logs_response.status_code == 200
    logs = logs_response.json()["items"]
    assert any(log["message"] == "Sync schedule triggered." for log in logs)


def test_daily_bars_schedule_trigger_requires_symbol(client):
    response = client.post("/api/sync-tasks/schedules/daily_bars_after_close/trigger")

    assert response.status_code == 400
    assert "股票代码" in response.json()["detail"]


def test_daily_bars_schedule_trigger_uses_schedule_scope_and_default_date_window(client):
    update_response = client.patch(
        "/api/sync-tasks/schedules/daily_bars_after_close",
        json={"source": "baostock", "symbol": "600519"},
    )
    assert update_response.status_code == 200

    response = client.post("/api/sync-tasks/schedules/daily_bars_after_close/trigger")

    assert response.status_code == 201
    task = response.json()
    assert task["task_type"] == "daily_bars"
    assert task["source"] == "baostock"
    assert task["market"] == "A_SHARE"
    assert task["symbol"] == "600519"
    assert task["start_date"] is not None
    assert task["end_date"] is not None
    assert (date.fromisoformat(task["end_date"]) - date.fromisoformat(task["start_date"])).days == 180


def test_calendar_schedule_trigger_uses_default_date_window(client):
    response = client.post("/api/sync-tasks/schedules/monthly_calendar_backfill/trigger")

    assert response.status_code == 201
    task = response.json()
    assert task["task_type"] == "calendars"
    assert task["source"] == "auto"
    assert task["market"] == "A_SHARE"
    assert task["start_date"] is not None
    assert task["end_date"] is not None


def test_sync_schedule_update_returns_404_for_unknown_code(client):
    response = client.patch("/api/sync-tasks/schedules/not-a-rule", json={"enabled": True})

    assert response.status_code == 404


def test_sync_schedule_trigger_returns_404_for_unknown_code(client):
    response = client.post("/api/sync-tasks/schedules/not-a-rule/trigger")

    assert response.status_code == 404
