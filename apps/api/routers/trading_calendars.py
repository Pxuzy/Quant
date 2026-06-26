from __future__ import annotations

from datetime import date


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from apps.api.db.session import get_db
from apps.api.schemas.sync_tasks import SyncTaskRead
from apps.api.schemas.trading_calendars import PaginatedTradingCalendars, TradingCalendarSyncRequest
from apps.api.services.trading_calendar_service import TradingCalendarService

router = APIRouter(prefix="/api/trading-calendars", tags=["trading-calendars"])


@router.get("", response_model=PaginatedTradingCalendars)
def list_trading_calendars(
    market: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    is_open: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=31, ge=1, le=366),
    db: Session = Depends(get_db),
) -> dict:
    return TradingCalendarService(db).list_days(
        market=market,
        start_date=start_date,
        end_date=end_date,
        is_open=is_open,
        page=page,
        page_size=page_size,
    )


@router.post("/sync", response_model=SyncTaskRead, status_code=status.HTTP_201_CREATED)
def sync_trading_calendars(request: TradingCalendarSyncRequest, db: Session = Depends(get_db)):
    try:
        return TradingCalendarService(db).create_calendar_sync_task(
            source=request.source,
            market=request.market,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
