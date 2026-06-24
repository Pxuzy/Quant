"""
MCP 数据定时拉取 — 通过 Hermes cron job 定时调用 MCP 工具，结果存入 SQLite
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 数据文件路径（JSON 格式缓存）— 使用绝对路径避免 uvicorn 工作目录问题
DATA_DIR = Path(r"E:\hermes\workspace\Quant\data\mcp_cache")
DATA_DIR.mkdir(parents=True, exist_ok=True)

INDUSTRY_FLOW_FILE = DATA_DIR / "industry_flow.json"
CONCEPT_FLOW_FILE = DATA_DIR / "concept_flow.json"
MAIN_FUND_FILE = DATA_DIR / "main_fund_rank.json"
NORTHBOUND_FILE = DATA_DIR / "northbound_flow.json"


def save_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: Path) -> Any | None:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def get_cached(path: Path, max_age_seconds: int = 60) -> Any | None:
    """获取缓存数据，超过 max_age 返回 None"""
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    age = datetime.now().timestamp() - mtime
    if age > max_age_seconds:
        return None
    return load_json(path)


# ── 对外接口（API 路由调用）──

def get_industry_flow(limit: int = 20) -> list[dict]:
    """获取行业板块资金流向（从 JSON 缓存）"""
    data = load_json(INDUSTRY_FLOW_FILE)
    if data is not None:
        items = data.get("data", data) if isinstance(data, dict) else data
        return items[:limit]
    return []


def get_concept_flow(limit: int = 20) -> list[dict]:
    """获取概念板块资金流向（从 JSON 缓存）"""
    data = load_json(CONCEPT_FLOW_FILE)
    if data is not None:
        items = data.get("data", data) if isinstance(data, dict) else data
        return items[:limit]
    return []


def get_main_fund_rank(limit: int = 20) -> list[dict]:
    """获取主力资金排名（从 JSON 缓存）"""
    data = load_json(MAIN_FUND_FILE)
    if data is not None:
        items = data.get("data", data) if isinstance(data, dict) else data
        return items[:limit]
    return []


def get_northbound_flow() -> dict:
    """获取北向资金数据（从 JSON 缓存）"""
    data = load_json(NORTHBOUND_FILE)
    if data is not None:
        return data.get("data", data)
    return {}


# ── 个股/搜索/K线（调用 MCP 工具，非缓存）──

def get_stock_quote_mcp(code: str) -> dict | None:
    """通过 eastmoney MCP 获取单只股票实时行情"""
    try:
        from mcp_eastmoney_get_stock_quote import get_stock_quote
        result = get_stock_quote(code=code)
        return result
    except Exception as e:
        logger.error(f"获取 {code} 行情失败: {e}")
        return None


def search_stock_mcp(keyword: str, limit: int = 10) -> list[dict]:
    """通过 eastmoney MCP 搜索股票"""
    try:
        from mcp_eastmoney_search_stock import search_stock
        result = search_stock(keyword=keyword, limit=limit)
        return result
    except Exception as e:
        logger.error(f"搜索股票失败: {e}")
        return []


def get_kline_mcp(code: str, period: str = "daily", limit: int = 100) -> list[dict]:
    """通过 eastmoney MCP 获取K线数据"""
    try:
        from mcp_eastmoney_get_kline import get_kline
        result = get_kline(code=code, period=period, limit=limit)
        return result
    except Exception as e:
        logger.error(f"获取 {code} K线失败: {e}")
        return []


def get_market_overview() -> dict:
    """市场全景概览"""
    try:
        from mcp_stock_sdk_get_a_share_quotes import get_a_share_quotes
        quotes = get_a_share_quotes(codes=["sh000001", "sz399001", "sh000300", "sz399006", "sh000688"])
        return {"indices": quotes, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"获取市场概览失败: {e}")
        return {"indices": []}


# ── 更新函数（由 cron job 调用）──

def update_industry_flow(limit: int = 30) -> list[dict]:
    """从 MCP 拉取行业板块资金流向并缓存"""
    try:
        # Direct MCP call via subprocess
        result = _call_mcp_eastmoney("industry", limit)
        if result:
            save_json(INDUSTRY_FLOW_FILE, result)
            logger.info(f"✅ 行业板块资金流向: {len(result)} 条")
        return result
    except Exception as e:
        logger.error(f"❌ 更新行业板块失败: {e}")
        return []


def update_concept_flow(limit: int = 30) -> list[dict]:
    """从 MCP 拉取概念板块资金流向并缓存"""
    try:
        result = _call_mcp_eastmoney("concept", limit)
        if result:
            save_json(CONCEPT_FLOW_FILE, result)
            logger.info(f"✅ 概念板块资金流向: {len(result)} 条")
        return result
    except Exception as e:
        logger.error(f"❌ 更新概念板块失败: {e}")
        return []


def update_main_fund_rank(limit: int = 30) -> list[dict]:
    """从 MCP 拉取主力资金排名并缓存"""
    try:
        result = _call_mcp_main_fund_rank(limit)
        if result:
            save_json(MAIN_FUND_FILE, result)
            logger.info(f"✅ 主力资金排名: {len(result)} 条")
        return result
    except Exception as e:
        logger.error(f"❌ 更新主力排名失败: {e}")
        return []


def update_northbound_flow() -> dict:
    """从 MCP 拉取北向资金数据并缓存"""
    try:
        result = _call_mcp_northbound()
        if result:
            save_json(NORTHBOUND_FILE, result)
            logger.info(f"✅ 北向资金数据已更新")
        return result
    except Exception as e:
        logger.error(f"❌ 更新北向资金失败: {e}")
        return {}


# ── MCP 调用（通过 Python import，因为 MCP server 是 subprocess）──

def _call_mcp_eastmoney(kind: str, limit: int) -> list[dict]:
    """调用 eastmoney MCP 板块资金流向"""
    try:
        from mcp_eastmoney_sector_fund_flow import sector_fund_flow
        return sector_fund_flow(kind=kind, limit=limit)
    except ImportError:
        # MCP tools are not importable as Python modules
        # Return empty, will be populated by cron job via Hermes tool calls
        logger.warning("MCP tools not importable as Python modules, use cron-based approach")
        return []


def _call_mcp_main_fund_rank(limit: int) -> list[dict]:
    """调用 eastmoney MCP 主力资金排名"""
    try:
        from mcp_eastmoney_main_fund_rank import main_fund_rank
        return main_fund_rank(limit=limit, market="all")
    except ImportError:
        return []


def _call_mcp_northbound() -> dict:
    """调用 stock_sdk MCP 北向资金"""
    try:
        from mcp_stock_sdk_get_northbound_flow_summary import get_northbound_flow_summary
        return get_northbound_flow_summary()
    except ImportError:
        return {}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    # This script is called by Hermes cron, which can use MCP tools
    # For standalone testing, we attempt direct import (will fail for MCP tools)
    print("MCP Data Service - Use Hermes cron jobs to update data")
    print("Available update functions:")
    print("  - update_industry_flow()")
    print("  - update_concept_flow()")
    print("  - update_main_fund_rank()")
    print("  - update_northbound_flow()")
