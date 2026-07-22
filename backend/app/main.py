from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import get_settings
from backend.app.db.session import init_db
from backend.app.routers import (
    data_quality,
    data_sources,
    database,
    datasets,
    health,
    market,
    market_data,
    research_data,
    stocks,
    sync_tasks,
    trading_calendars,
    watchlist,
)

# 前端 dist 路径
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
INDEX_HTML = FRONTEND_DIST / "index.html"


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

    # 挂载前端静态资源（JS/CSS/图片）
    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

        @app.get("/", include_in_schema=False)
        async def serve_root():
            return FileResponse(str(INDEX_HTML))

        # SPA fallback: 所有非 API 路径都返回 index.html
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/") or full_path.startswith("health"):
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(str(INDEX_HTML))

    return app


app = create_app()
