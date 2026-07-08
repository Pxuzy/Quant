from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.data_sources import (
    DataSourceCatalogItemRead,
    DataSourceHealthRead,
    DataSourceRead,
    DataSourceSmokeRead,
    DataSourceUpdate,
)
from backend.app.services.data_source_service import DataSourceService

router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])


@router.get("", response_model=list[DataSourceRead])
def list_data_sources(db: Session = Depends(get_db)):
    return DataSourceService(db).list_sources()


@router.get("/catalog", response_model=list[DataSourceCatalogItemRead])
def list_data_source_catalog(db: Session = Depends(get_db)):
    return DataSourceService(db).list_catalog()


@router.patch("/{code}", response_model=DataSourceRead)
def update_data_source(code: str, request: DataSourceUpdate, db: Session = Depends(get_db)):
    source = DataSourceService(db).update_source(code, enabled=request.enabled, priority=request.priority)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Data source '{code}' not found.")
    return source


@router.post("/{code}/health-check", response_model=DataSourceHealthRead)
def check_data_source_health(code: str, db: Session = Depends(get_db)):
    try:
        return DataSourceService(db).check_source_health(code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{code}/smoke-test", response_model=DataSourceSmokeRead)
def smoke_test_data_source(code: str, capability: str | None = Query(default=None), db: Session = Depends(get_db)):
    try:
        return DataSourceService(db).smoke_test_source(code, capability=capability)
    except ValueError as exc:
        if "Unsupported smoke capability" in str(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
