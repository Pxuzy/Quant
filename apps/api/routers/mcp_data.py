"""
MCP 增强数据 API — 通过 MCP 工具获取板块、资金流向等实时数据
"""

from __future__ import annotations


from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/mcp", tags=["mcp-data"])


@router.get("/industry-flow")
async def get_industry_flow(limit: int = Query(20, description="条数")):
    """行业板块资金流向（实时）"""
    from apps.api.services.mcp_data_service import get_industry_flow
    return get_industry_flow(limit=limit)


@router.get("/concept-flow")
async def get_concept_flow(limit: int = Query(20, description="条数")):
    """概念板块资金流向（实时）"""
    from apps.api.services.mcp_data_service import get_concept_flow
    return get_concept_flow(limit=limit)


@router.get("/main-fund-rank")
async def get_main_fund_rank(
    limit: int = Query(20, description="条数"),
    market: str = Query("all", description="市场过滤"),
):
    """主力资金净流入排名"""
    from apps.api.services.mcp_data_service import get_main_fund_rank
    return get_main_fund_rank(limit=limit)


@router.get("/stock-quote")
async def get_stock_quote(code: str = Query(..., description="股票代码")):
    """单只股票实时行情（MCP）"""
    from apps.api.services.mcp_data_service import get_stock_quote_mcp
    result = get_stock_quote_mcp(code)
    if result is None:
        return {"error": f"未找到 {code}"}
    return result


@router.get("/search")
async def search_stock(
    keyword: str = Query(..., description="搜索关键词"),
    limit: int = Query(10, description="条数"),
):
    """股票搜索（MCP）"""
    import urllib.parse
    from apps.api.services.mcp_data_service import search_stock_mcp
    # URL-encode keyword to avoid ASCII encoding issue with Chinese
    encoded = urllib.parse.quote(keyword)
    return search_stock_mcp(encoded, limit)


@router.get("/kline")
async def get_kline(
    code: str = Query(..., description="股票代码"),
    period: str = Query("daily", description="周期: daily/weekly/monthly"),
    limit: int = Query(100, description="条数"),
):
    """K线数据（MCP）"""
    from apps.api.services.mcp_data_service import get_kline_mcp
    return get_kline_mcp(code, period, limit)


@router.get("/market-overview")
async def get_market_overview():
    """市场全景概览（指数+板块+资金）"""
    from apps.api.services.mcp_data_service import get_market_overview
    return get_market_overview()
