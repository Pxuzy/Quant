from __future__ import annotations

import pytest

from backend.app.db.session import SessionLocal
from backend.app.models import SyncTask
from backend.app.models.entities import utcnow
from backend.app.repositories.sync_tasks import SyncTaskRepository
from datetime import timedelta


def test_sync_task_read_exposes_auto_task_candidate_and_selected_sources(client, fake_akshare):
    response = client.post("/api/stocks/sync", json={"source": "auto", "market": "A_SHARE"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["candidate_sources"]
    assert payload["selected_source"] is None


def test_sync_task_read_populates_candidate_and_selected_sources_from_logs(client, fake_akshare):
    response = client.post("/api/stocks/sync", json={"source": "auto", "market": "A_SHARE"})

    assert response.status_code == 201
    payload = response.json()

    db = SessionLocal()
    try:
        task = db.get(SyncTask, payload["id"])
        assert task is not None
        assert task.logs[0].payload_json["candidate_sources"]
    finally:
        db.close()

    assert payload["source"] == "auto"
    assert payload["candidate_sources"]
    assert payload["selected_source"] is None


def test_sync_task_claim_heartbeat_and_partial_success_are_persisted(client):
    db = SessionLocal()
    try:
        task = SyncTask(task_type="daily_bars_market_repair", source="fixture", market="A_SHARE")
        db.add(task)
        db.commit()
        repository = SyncTaskRepository(db)

        repository.mark_running(task, owner="worker-a", lease_seconds=60)
        assert task.lease_owner == "worker-a"
        assert task.attempt == 1
        assert task.heartbeat_at is not None
        assert task.lease_expires_at is not None

        previous_heartbeat = task.heartbeat_at
        assert repository.heartbeat(task, owner="worker-a", lease_seconds=60) is True
        assert task.heartbeat_at >= previous_heartbeat
        assert repository.heartbeat(task, owner="worker-b", lease_seconds=60) is False

        repository.complete(
            task,
            records_read=10,
            records_written=8,
            failed_symbols=["000001"],
            failed_chunks=["000001:2026-06-01:2026-06-02"],
            failure_reason="one symbol failed",
        )
        db.commit()

        assert task.status == "partial_success"
        assert task.failed_symbols == ["000001"]
        assert task.failed_chunks == ["000001:2026-06-01:2026-06-02"]
        assert task.failure_reason == "one symbol failed"
        assert task.lease_owner is None
    finally:
        db.close()


def test_sync_task_recovery_uses_expired_lease_and_keeps_attempt_count(client):
    db = SessionLocal()
    try:
        task = SyncTask(
            task_type="daily_bars",
            source="fixture",
            status="running",
            attempt=3,
            started_at=utcnow() - timedelta(hours=2),
            heartbeat_at=utcnow() - timedelta(hours=1),
            lease_expires_at=utcnow() - timedelta(minutes=1),
            lease_owner="dead-worker",
        )
        db.add(task)
        db.commit()

        assert SyncTaskRepository(db).recover_stale_tasks() == 1
        db.refresh(task)
        assert task.status == "pending"
        assert task.attempt == 3
        assert task.lease_owner is None
        assert task.error_message is not None
    finally:
        db.close()


def test_sync_task_lost_lease_blocks_further_work(client):
    db = SessionLocal()
    try:
        task = SyncTask(task_type="daily_bars", source="fixture")
        db.add(task)
        db.commit()
        repository = SyncTaskRepository(db)
        repository.mark_running(task, owner="worker-a", lease_seconds=60)
        db.query(SyncTask).filter(SyncTask.id == task.id).update({"lease_owner": "worker-b"})
        db.commit()
        db.refresh(task)

        with pytest.raises(RuntimeError, match="lost its worker lease"):
            repository.require_heartbeat(task)
    finally:
        db.close()
