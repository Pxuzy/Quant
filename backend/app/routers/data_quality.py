from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.data_quality import (
    DataQualityCheckResult,
    DataQualityCheckRunList,
    DataQualityOverview,
    PaginatedDataQualityReports,
)
from backend.app.services.data_quality_service import DataQualityService

router = APIRouter(prefix="/api/data-quality", tags=["data-quality"])


@router.get("/overview", response_model=DataQualityOverview)
def get_data_quality_overview(db: Session = Depends(get_db)) -> dict:
    return DataQualityService(db).get_overview()


@router.get("/reports", response_model=PaginatedDataQualityReports)
def list_data_quality_reports(
    dataset_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    checked_at: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    parsed_checked_at = checked_at.replace(tzinfo=None) if checked_at else None
    return DataQualityService(db).list_reports(
        dataset_name=dataset_name,
        status=status,
        severity=severity,
        checked_at=parsed_checked_at,
        page=page,
        page_size=page_size,
    )


@router.get("/check-runs", response_model=DataQualityCheckRunList)
def list_data_quality_check_runs(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    return DataQualityService(db).list_check_runs(limit=limit)


@router.post("/check", response_model=DataQualityCheckResult)
def run_data_quality_check(db: Session = Depends(get_db)) -> dict:
    return DataQualityService(db).run_check()
