"""板块服务公共 API。"""

import logging
from typing import Dict, List, Optional

from backend.app.db.session import SessionLocal, get_engine
from backend.app.repositories.stock_boards import StockBoardRepository
from backend.app.services import quote_service as _qs
from backend.app.services._utils import _clean_text, _exchange_from_symbol, _stock_quote_code
from backend.app.services.ths_sector_fetcher import (
    SECTOR_CATEGORY_ORDER,
    STATIC_BOARD_CODE_MAP,
    STATIC_BOARD_LEGACY_CODE_MAP,
    _db_board_stocks,
    _ensure_ths_industry_boards,
    _load_ths_map,
    _static_sector_rankings,
)

logger = logging.getLogger(__name__)


def get_sector_rankings(categories: Optional[List[str]] = None) -> List[Dict]:
    """获取板块排行"""
    requested = [c for c in (categories or SECTOR_CATEGORY_ORDER) if c in SECTOR_CATEGORY_ORDER]
    if not requested:
        requested = SECTOR_CATEGORY_ORDER
    rows: list[dict] = []
    static_categories = list(requested)
    if "行业板块" in requested:
        ths_rows = _ensure_ths_industry_boards()
        if ths_rows:
            rows.extend(ths_rows)
            static_categories = [c for c in static_categories if c != "行业板块"]
    rows.extend(_static_sector_rankings(static_categories))
    grouped: list[dict] = []
    for cat in requested:
        cat_rows = sorted(
            [r for r in rows if r["category"] == cat],
            key=lambda x: x["change_pct"],
            reverse=True,
        )
        grouped.extend(cat_rows)
    return grouped


def get_stock_sectors(code: str) -> List[str]:
    """获取股票所属的同花顺一级行业板块列表"""
    symbol = code.replace("sh", "").replace("sz", "").replace("bj", "")
    exchange = _exchange_from_symbol(symbol)
    try:
        get_engine()
        db = SessionLocal()
        try:
            repo = StockBoardRepository(db)
            sectors = [
                b.name
                for b in repo.list_boards(category="行业板块")
                for m in repo.list_members(board=b)
                if m.symbol == symbol and m.exchange == exchange
            ]
            if sectors:
                return sectors
        finally:
            db.close()
    except Exception as exc:
        logger.warning("数据库股票板块查询失败: %s", exc)
    return _load_ths_map().get("stock_to_sectors", {}).get(symbol, [])


def get_sector_stocks(sector_name: str = "能源金属", category: str | None = None) -> List[Dict]:
    """获取板块成分股实时行情"""
    normalized_category = _clean_text(category)
    if normalized_category == "行业板块":
        _ensure_ths_industry_boards()
        rows = _db_board_stocks(sector_name, category=normalized_category)
        if rows:
            return rows
        stocks = _load_ths_map().get("sector_to_stocks", {}).get(sector_name, [])
        codes = [_stock_quote_code(s, _exchange_from_symbol(s)) for s in stocks]
    elif normalized_category:
        codes = STATIC_BOARD_CODE_MAP.get((normalized_category, sector_name), [])
    else:
        rows = _db_board_stocks(sector_name, category=None)
        if rows:
            return rows
        stocks = _load_ths_map().get("sector_to_stocks", {}).get(sector_name, [])
        if stocks:
            codes = [_stock_quote_code(s, _exchange_from_symbol(s)) for s in stocks]
        else:
            codes = STATIC_BOARD_LEGACY_CODE_MAP.get(sector_name, [])
    quotes = _qs.get_realtime_quotes(codes)
    for q in quotes:
        q["sectors"] = [sector_name]
    return quotes


def get_sector_constituents(sector_name: str) -> List[Dict]:
    """获取板块成分股实时行情"""
    return get_sector_stocks(sector_name)
