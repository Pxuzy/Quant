from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.models import Dataset
from backend.app.repositories.stocks import StockRepository


def project_dataset_row_count(db: Session, dataset: Dataset) -> int:
    if dataset.name != "stocks":
        return dataset.row_count

    return project_stock_dataset_row_count(db, dataset)


def sync_projected_dataset_row_count(db: Session, dataset: Dataset) -> int:
    projected_count = project_dataset_row_count(db, dataset)
    if projected_count != dataset.row_count:
        dataset.row_count = projected_count
        dataset.quality_status = "good" if projected_count > 0 else "warning"
        db.flush()
    return projected_count


def project_stock_dataset_row_count(db: Session, dataset: Dataset) -> int:
    stock_repo = StockRepository(db)
    stock_pool_market = "A_SHARE"
    raw_row_count = stock_repo.count(market=stock_pool_market, common_only=False)
    common_row_count = stock_repo.count(market=stock_pool_market, common_only=True)

    if raw_row_count > 0 and dataset.row_count == raw_row_count and 0 < common_row_count < raw_row_count:
        return common_row_count

    return dataset.row_count
