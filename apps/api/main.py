from __future__ import annotations

from apps.api.core.fastapi_compat import apply_starlette_router_compat

apply_starlette_router_compat()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import get_settings
from apps.api.db.session import init_db
from apps.api.routers import (
    data_quality,
    data_sources,
    datasets,
    database,
    health,
    market,
    market_data,
    mcp_data,
    research_data,
    stocks,
    sync_tasks,
    trading_calendars,
    watchlist,
)


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(market.router)
    app.include_router(mcp_data.router)
    app.include_router(database.router)
    app.include_router(data_quality.router)
    app.include_router(data_sources.router)
    app.include_router(datasets.router)
    app.include_router(market_data.router)
    app.include_router(research_data.router)
    app.include_router(stocks.router)
    app.include_router(sync_tasks.router)
    app.include_router(trading_calendars.router)
    app.include_router(watchlist.router)
    return app


app = create_app()
