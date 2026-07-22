from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.sync_tasks import (
    PaginatedSyncTasks,
    SyncRunnerStatusRead,
    SyncScheduleRead,
    SyncSchedulesRead,
    SyncScheduleUpdate,
    SyncTaskIngestBatchesRead,
    SyncTaskLogsRead,
    SyncTaskRead,
)
from backend.app.services.sync_task_service import SyncScheduleService
from backend.app.services.sync_task_service import SyncTaskService

router = APIRouter(prefix="/api/sync-tasks", tags=["sync-tasks"])


@router.get("", response_model=PaginatedSyncTasks)
def list_sync_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    market: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return SyncTaskService(db).list_tasks(
        status=status_filter,
        source=source,
        task_type=task_type,
        market=market,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )


@router.get("/schedules", response_model=SyncSchedulesRead)
def list_sync_schedules(db: Session = Depends(get_db)) -> dict:
    return SyncScheduleService(db).list_schedules()


@router.get("/runner-status", response_model=SyncRunnerStatusRead)
def get_sync_runner_status(db: Session = Depends(get_db)) -> dict:
    return SyncTaskService(db).get_runner_status()


@router.patch("/schedules/{code}", response_model=SyncScheduleRead)
def update_sync_schedule(code: str, request: SyncScheduleUpdate, db: Session = Depends(get_db)):
    try:
        schedule = SyncScheduleService(db).update_schedule(
            code,
            enabled=request.enabled,
            cron_expression=request.cron_expression,
            source=request.source,
            market=request.market,
            symbol=request.symbol,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sync schedule '{code}' not found.")
    return schedule


@router.post("/schedules/{code}/trigger", response_model=SyncTaskRead, status_code=status.HTTP_201_CREATED)
def trigger_sync_schedule(code: str, db: Session = Depends(get_db)):
    try:
        task = SyncScheduleService(db).trigger_schedule(code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sync schedule '{code}' not found.")
    return task


@router.get("/{task_id}", response_model=SyncTaskRead)
def get_sync_task(task_id: int, db: Session = Depends(get_db)):
    task = SyncTaskService(db).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sync task {task_id} not found.")
    return task


@router.get("/{task_id}/logs", response_model=SyncTaskLogsRead)
def list_sync_task_logs(task_id: int, db: Session = Depends(get_db)) -> dict:
    logs = SyncTaskService(db).get_task_logs(task_id)
    if logs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sync task {task_id} not found.")
    return logs


@router.get("/{task_id}/ingest-batches", response_model=SyncTaskIngestBatchesRead)
def list_sync_task_ingest_batches(task_id: int, db: Session = Depends(get_db)) -> dict:
    batches = SyncTaskService(db).get_task_ingest_batches(task_id)
    if batches is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sync task {task_id} not found.")
    return batches
