from __future__ import annotations

from datetime import date

from apps.api.core.fastapi_compat import apply_starlette_router_compat

apply_starlette_router_compat()

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from apps.api.db.session import get_db
from apps.api.schemas.market_data import (
    DailyBarsMarketRepairPreviewResponse,
    DailyBarsMarketRepairRequest,
    DailyBarsSyncRequest,
    PaginatedDailyBars,
)
from apps.api.schemas.sync_tasks import SyncTaskRead
from apps.api.services.market_data_query_service import MarketDataQueryService
from apps.api.services.market_data_sync_service import MarketDataSyncService

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
    return MarketDataQueryService().list_daily_bars(
        symbol=symbol,
        market=market,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_order=sort_order,
    )


@router.get("/daily-bars/{symbol}", response_model=PaginatedDailyBars)
def list_daily_bars_by_symbol(
    symbol: str,
    market: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=1000),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> dict:
    return MarketDataQueryService().list_daily_bars(
        symbol=symbol,
        market=market,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_order=sort_order,
    )


@router.post("/daily-bars/sync", response_model=SyncTaskRead, status_code=status.HTTP_201_CREATED)
def sync_daily_bars(request: DailyBarsSyncRequest, db: Session = Depends(get_db)):
    try:
        return MarketDataSyncService(db).create_daily_bars_sync_task(
            source=request.source,
            market=request.market,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
