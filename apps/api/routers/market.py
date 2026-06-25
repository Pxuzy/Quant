"""市场数据 API 路由 - 实时行情、K线、新闻"""

from __future__ import annotations

from apps.api.core.fastapi_compat import apply_starlette_router_compat

apply_starlette_router_compat()

from fastapi import APIRouter, Query

from apps.api.services.market_service import (
    get_history_kline,
    get_index_quotes,
    get_news,
    get_realtime_quotes,
    get_sector_rankings,
    get_sector_stocks,
    get_sector_constituents,
    get_stock_sectors,
    search_stock,
    sync_ths_industry_boards,
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
    keyword: str | None = Query(None, description="搜索关键词（可选）"),
    limit: int = Query(20, description="条数"),
    page: int = Query(1, description="页码"),
):
    """新闻（从DB读取，由定时任务填充）"""
    from apps.api.db.session import SessionLocal
    from apps.api.repositories.news_articles import NewsRepository
    
    db = SessionLocal()
    try:
        repo = NewsRepository(db)
        articles, total = repo.list_news(keyword=keyword, page=page, page_size=limit)
        return {
            "items": [
                {
                    "id": a.id,
                    "title": a.title,
                    "url": a.url,
                    "summary": a.summary,
                    "source": a.source,
                    "category": a.category,
                    "related_symbols": a.related_symbols,
                    "published_at": a.published_at.isoformat() if a.published_at else None,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in articles
            ],
            "total": total,
            "page": page,
            "page_size": limit,
        }
    finally:
        db.close()


@router.post("/news/ingest")
def trigger_news_ingest():
    """手动触发新闻抓取"""
    from apps.api.services.news_ingest_service import run_news_ingest
    result = run_news_ingest()
    return result


@router.get("/search")
def search(
    keyword: str = Query(..., description="搜索关键词"),
    limit: int = Query(10, description="条数"),
):
    return search_stock(keyword, limit)


@router.get("/sector")
def get_sector(
    name: str = Query("能源金属", description="板块名称，如 能源金属、半导体、人工智能"),
    category: str | None = Query("行业板块", description="板块分类"),
):
    return get_sector_stocks(name, category=category)


@router.get("/sectors")
def get_sectors(
    categories: str | None = Query(None, description="逗号分隔板块分类，如 行业板块,概念板块,指数板块"),
):
    category_list = [item.strip() for item in categories.split(",") if item.strip()] if categories else None
    return get_sector_rankings(category_list)


@router.post("/sectors/sync")
def sync_sectors(
    include_members: bool = Query(True, description="是否同步板块成分股并更新股票行业"),
    limit: int | None = Query(None, ge=1, description="限制同步板块数量，调试用"),
):
    return sync_ths_industry_boards(include_members=include_members, limit=limit)


@router.get("/sector-constituents")
def get_sector_constituents_api(
    name: str = Query(..., description="板块名称，如 半导体、人工智能"),
):
    """获取板块成分股实时行情"""
    return get_sector_constituents(name)


@router.get("/stock-sectors")
def get_stock_sectors_api(
    code: str = Query(..., description="股票代码，如 sh600900"),
):
    """获取股票所属板块列表"""
    return {"code": code, "sectors": get_stock_sectors(code)}
