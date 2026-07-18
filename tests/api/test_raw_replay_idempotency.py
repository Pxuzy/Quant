from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.models import RawArtifact, SyncTask
from backend.app.repositories.sync_tasks import SyncTaskRepository


def test_active_raw_replay_identity_is_atomic_under_concurrent_enqueue(client):
    setup_db = SessionLocal()
    try:
        source_task = SyncTask(task_type="daily_bars", source="fixture", market="A_SHARE")
        setup_db.add(source_task)
        setup_db.commit()
        setup_db.refresh(source_task)
        artifact = RawArtifact(
            task_id=source_task.id,
            dataset_name="daily_bars",
            source="fixture",
            requested_source="fixture",
            market="A_SHARE",
            symbol="600519",
            uri="/tmp/raw-artifact.json",
            sha256="0" * 64,
            byte_size=2,
            row_count=0,
            adjust_type="none",
        )
        setup_db.add(artifact)
        setup_db.commit()
        setup_db.refresh(artifact)
        artifact_id = artifact.id
    finally:
        setup_db.close()

    barrier = Barrier(2)

    def enqueue() -> tuple[int, bool]:
        db = SessionLocal()
        try:
            barrier.wait(timeout=5)
            task, created = SyncTaskRepository(db).create_or_get_active_raw_replay_task(
                raw_artifact_id=artifact_id,
                adjust_type="none",
                market="A_SHARE",
                symbol="600519",
                start_date=None,
                end_date=None,
            )
            db.commit()
            return task.id, created
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: enqueue(), range(2)))

    assert len({task_id for task_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1

    verify_db = SessionLocal()
    try:
        active_tasks = list(
            verify_db.scalars(
                select(SyncTask).where(
                    SyncTask.task_type == "daily_bars_raw_replay",
                    SyncTask.input_raw_artifact_id == artifact_id,
                    SyncTask.adjust_type == "none",
                    SyncTask.status.in_(["pending", "running"]),
                )
            )
        )
    finally:
        verify_db.close()
    assert len(active_tasks) == 1
