from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from apps.api.schemas.research_data import ResearchBarsRead
from apps.api.services.research_data_service import ResearchDataService

router = APIRouter(prefix="/api/research-data", tags=["research-data"])


@router.get("/bars", response_model=ResearchBarsRead)
def read_bars(
    symbol: str = Query(min_length=1),
    market: str = Query(default="A_SHARE", min_length=1),
    start_date: date = Query(),
    end_date: date = Query(),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5000, ge=1, le=10000),
) -> dict:
    try:
        return ResearchDataService().read_bars(
            symbol=symbol,
            market=market,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
