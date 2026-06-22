"""市场数据 API 路由 - 实时行情、K线、新闻"""

from __future__ import annotations

from apps.api.core.fastapi_compat import apply_starlette_router_compat

apply_starlette_router_compat()

from fastapi import APIRouter, Query

from quant.services.market_service import (
    get_history_kline,
    get_index_quotes,
    get_news,
    get_realtime_quotes,
    get_sector_stocks,
    search_stock,
)

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/quote")
def get_quotes(codes: str = Query(..., description="逗号分隔股票代码，如 sh600900,sz000858")):
    return get_realtime_quotes(codes.split(","))


@router.get("/index")
def get_indices():
    return get_index_quotes()


@router.get("/kline")
def get_kline(
    code: str = Query(..., description="股票代码，如 sh600900"),
    period: str = Query("day", description="day/week/month"),
    count: int = Query(100, description="条数"),
    adjust: str = Query("qfq", description="qfq/hfq/空"),
):
    return get_history_kline(code, period, count, adjust)


@router.get("/news")
def get_news_list(
    keyword: str = Query("A股", description="搜索关键词"),
    limit: int = Query(20, description="条数"),
    page: int = Query(1, description="页码"),
):
    return get_news(keyword, limit, page)


@router.get("/search")
def search(
    keyword: str = Query(..., description="搜索关键词"),
    limit: int = Query(10, description="条数"),
):
    return search_stock(keyword, limit)


@router.get("/sector")
def get_sector(
    name: str = Query("电力", description="板块名称"),
):
    return get_sector_stocks(name)
