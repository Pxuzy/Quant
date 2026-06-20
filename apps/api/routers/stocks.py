from __future__ import annotations

from apps.api.core.fastapi_compat import apply_starlette_router_compat

apply_starlette_router_compat()

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from apps.api.db.session import get_db
from apps.api.schemas.stocks import (
    PaginatedStocks,
    StockDailyIngestBatchesRead,
    StockDailyCoverageRead,
    StockDailyQualityRead,
    StockRead,
    StockSyncRequest,
)
from apps.api.schemas.sync_tasks import SyncTaskRead
from apps.api.services.stock_query_service import StockQueryService
from apps.api.services.stock_sync_service import StockSyncService

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("", response_model=PaginatedStocks)
def list_stocks(
    keyword: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    market: str | None = Query(default=None),
    common_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    return StockQueryService(db).list_stocks(
        keyword=keyword,
        status=status_filter,
        market=market,
        common_only=common_only,
        page=page,
        page_size=page_size,
    )


@router.get("/{symbol}", response_model=StockRead)
def get_stock(
    symbol: str,
    market: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stock = StockQueryService(db).get_stock(symbol=symbol, market=market)
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found.")
    return stock


@router.get("/{symbol}/daily-coverage", response_model=StockDailyCoverageRead)
def get_stock_daily_coverage(
    symbol: str,
    market: str | None = Query(default="A_SHARE"),
    db: Session = Depends(get_db),
) -> dict:
    coverage = StockQueryService(db).get_daily_coverage(symbol=symbol, market=market)
    if coverage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found.")
    return coverage


@router.get("/{symbol}/daily-quality", response_model=StockDailyQualityRead)
def get_stock_daily_quality(
    symbol: str,
    market: str | None = Query(default="A_SHARE"),
    db: Session = Depends(get_db),
) -> dict:
    quality = StockQueryService(db).get_daily_quality(symbol=symbol, market=market)
    if quality is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found.")
    return quality


@router.get("/{symbol}/daily-ingest-batches", response_model=StockDailyIngestBatchesRead)
def get_stock_daily_ingest_batches(
    symbol: str,
    market: str | None = Query(default="A_SHARE"),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict:
    batches = StockQueryService(db).get_daily_ingest_batches(symbol=symbol, market=market, limit=limit)
    if batches is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found.")
    return batches


@router.post("/sync", response_model=SyncTaskRead, status_code=status.HTTP_201_CREATED)
def sync_stocks(request: StockSyncRequest | None = None, db: Session = Depends(get_db)):
    payload = request or StockSyncRequest()
    try:
        return StockSyncService(db).create_stock_sync_task(source=payload.source, market=payload.market)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
