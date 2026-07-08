from __future__ import annotations

from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Dataset
from backend.app.services.dataset_row_count_projection import sync_projected_dataset_row_count


class DatasetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_datasets(
        self,
        *,
        name: str | None,
        layer: str | None,
        storage_type: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        conditions = []
        if name:
            conditions.append(Dataset.name.ilike(f"%{name.strip()}%"))
        if layer:
            conditions.append(Dataset.layer == layer.strip())
        if storage_type:
            conditions.append(Dataset.storage_type == storage_type.strip())

        total_stmt = select(func.count(Dataset.id))
        records_stmt = select(Dataset).order_by(Dataset.layer.asc(), Dataset.name.asc())
        if conditions:
            total_stmt = total_stmt.where(*conditions)
            records_stmt = records_stmt.where(*conditions)

        total = self.db.scalar(total_stmt) or 0
        items = self.db.scalars(records_stmt.offset((page - 1) * page_size).limit(page_size)).all()
        items = [_dataset_read(dataset, self.db) for dataset in items]
        self.db.commit()
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": ceil(total / page_size) if total else 0,
        }

    def get_dataset(self, name: str) -> dict | None:
        dataset = self.db.scalar(select(Dataset).where(Dataset.name == name))
        if dataset is None:
            return None
        payload = _dataset_read(dataset, self.db)
        self.db.commit()
        return payload


def _dataset_read(dataset: Dataset, db: Session) -> dict:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "layer": dataset.layer,
        "storage_type": dataset.storage_type,
        "path": dataset.path,
        "schema_json": dataset.schema_json,
        "primary_keys_json": dataset.primary_keys_json,
        "partition_keys_json": dataset.partition_keys_json,
        "source": dataset.source,
        "row_count": sync_projected_dataset_row_count(db, dataset),
        "latest_data_date": dataset.latest_data_date,
        "quality_status": dataset.quality_status,
        "updated_at": dataset.updated_at,
    }
