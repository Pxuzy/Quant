from __future__ import annotations

from datetime import date


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.market_data import (
    DailyBarsMarketRepairPreviewResponse,
    DailyBarsMarketRepairRequest,
    DailyBarsSyncRequest,
    PaginatedDailyBars,
)
from backend.app.schemas.sync_tasks import SyncTaskRead
from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.services.sync_service import MarketDataSyncService

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("/daily-bars", response_model=PaginatedDailyBars)
def list_daily_bars(
    symbol: str | None = Query(default=None),
    market: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=1000),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> dict:
    return _list_daily_bars(
        symbol=symbol,
        market=market,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_order=sort_order,
    )


def _list_daily_bars(
    symbol: str | None,
    market: str | None,
    start_date: date | None,
    end_date: date | None,
    page: int,
    page_size: int,
    sort_order: str,
) -> dict:
    repo = DailyBarRepository()
    items, total = repo.list_daily_bars(
        symbol=symbol,
        market=market,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_order=sort_order,
    )
    from math import ceil
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    }


@router.post("/daily-bars/sync", response_model=SyncTaskRead, status_code=status.HTTP_201_CREATED)
def sync_daily_bars(request: DailyBarsSyncRequest, db: Session = Depends(get_db)):
    try:
        return MarketDataSyncService(db).create_daily_bars_sync_task(
            source=request.source,
            market=request.market,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            adjust_type=request.adjust_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/daily-bars/market-repair/preview", response_model=DailyBarsMarketRepairPreviewResponse)
def preview_market_daily_bars_repair(request: DailyBarsMarketRepairRequest, db: Session = Depends(get_db)):
    try:
        return MarketDataSyncService(db).preview_market_daily_bars_repair(
            source=request.source,
            market=request.market,
            start_date=request.start_date,
            end_date=request.end_date,
            max_symbols=request.max_symbols,
            start_policy=request.start_policy,
            adjust_type=request.adjust_type,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/daily-bars/market-repair", response_model=SyncTaskRead, status_code=status.HTTP_201_CREATED)
def repair_market_daily_bars(request: DailyBarsMarketRepairRequest, db: Session = Depends(get_db)):
    try:
        return MarketDataSyncService(db).create_market_daily_bars_repair_task(
            source=request.source,
            market=request.market,
            start_date=request.start_date,
            end_date=request.end_date,
            max_symbols=request.max_symbols,
            start_policy=request.start_policy,
            adjust_type=request.adjust_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
