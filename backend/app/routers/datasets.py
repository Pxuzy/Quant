from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.datasets import DatasetRead, PaginatedDatasets
from backend.app.services.dataset_service import DatasetService

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", response_model=PaginatedDatasets)
def list_datasets(
    name: str | None = Query(default=None),
    layer: str | None = Query(default=None),
    storage_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return DatasetService(db).list_datasets(
        name=name,
        layer=layer,
        storage_type=storage_type,
        page=page,
        page_size=page_size,
    )


@router.get("/{name}", response_model=DatasetRead)
def get_dataset(name: str, db: Session = Depends(get_db)):
    dataset = DatasetService(db).get_dataset(name)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset '{name}' not found.")
    return dataset
