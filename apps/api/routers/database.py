from __future__ import annotations

from datetime import date

from apps.api.core.fastapi_compat import apply_starlette_router_compat

apply_starlette_router_compat()

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.db.session import get_db
from apps.api.schemas.database import DatabaseIntegrationOverviewRead, DatabaseLineageRead, DatabaseStatusRead
from apps.api.services.database_integration_service import DEFAULT_COVERAGE_MARKET
from apps.api.services.database_integration_service import DatabaseIntegrationService
from apps.api.services.database_status_service import DatabaseStatusService

router = APIRouter(prefix="/api/database", tags=["database"])


@router.get("/status", response_model=DatabaseStatusRead)
def get_database_status() -> dict:
    return DatabaseStatusService().get_status()


@router.get("/integration-overview", response_model=DatabaseIntegrationOverviewRead)
def get_database_integration_overview(
    market: str = Query(default=DEFAULT_COVERAGE_MARKET),
    db: Session = Depends(get_db),
) -> dict:
    return DatabaseIntegrationService(db).get_overview(market=market)


@router.get("/lineage", response_model=DatabaseLineageRead)
def list_database_lineage(
    batch_id: int | None = Query(default=None, ge=1),
    dataset_name: str | None = Query(default=None),
    market: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    trade_date: date | None = Query(default=None),
    source: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    return DatabaseIntegrationService(db).list_lineage(
        batch_id=batch_id,
        dataset_name=dataset_name,
        market=market,
        symbol=symbol,
        trade_date=trade_date,
        source=source,
        status=status,
        page=page,
        page_size=page_size,
    )
