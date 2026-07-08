from __future__ import annotations

from backend.app.db.session import SessionLocal
from backend.app.models import SyncTask


def test_sync_task_read_exposes_auto_task_candidate_and_selected_sources(client):
    response = client.post("/api/stocks/sync", json={"source": "auto", "market": "A_SHARE"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["candidate_sources"]
    assert payload["selected_source"] is None


def test_sync_task_read_populates_candidate_and_selected_sources_from_logs(client):
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
