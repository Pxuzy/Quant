"""市场数据服务 - 提供统一的数据获取接口

已验证可用的数据源:
  - 腾讯实时行情: qt.gtimg.cn (直连, 无需代理)
  - 腾讯历史K线: web.ifzq.gtimg.cn (直连, 需带日期范围)
  - 新浪新闻: feed.mix.sina.com.cn (直连)

不可用的数据源 (已验证):
  - 雪球: 404
  - 东方财富K线: 连接关闭
  - 腾讯板块行情: 返回空
"""

import urllib.request
import urllib.parse
import json
import re
import logging
import contextlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from html.parser import HTMLParser
from importlib import import_module
from pathlib import Path
from typing import List, Dict, Optional

from apps.api.db.session import SessionLocal, get_engine
from apps.api.repositories.stock_boards import StockBoardRepository
from apps.api.repositories.stocks import StockRepository

logger = logging.getLogger(__name__)

# ── THS 同花顺一级行业板块映射缓存 ──
THS_SECTOR_MAP_PATH = Path(__file__).resolve().parents[3] / "data" / "mcp_cache" / "ths_sector_map.json"

# THS 同花顺一级行业板块列表（14个）
THS_INDUSTRY_SECTORS = [
    "能源金属", "半导体", "元件", "电子化学品", "化学纤维",
    "军工电子", "消费电子", "医疗服务", "光学光电子", "其他电子",
    "小金属", "贵金属", "机场航运", "工业金属",
]
SECTOR_CATEGORY_ORDER = ["行业板块", "概念板块", "指数板块"]
STATIC_BOARD_GROUPS = [
    {"name": "人工智能", "category": "概念板块", "codes": ["sz300033", "sh600570", "sz300418", "sh688256", "sz002230", "sh603019"]},
    {"name": "新能源车", "category": "概念板块", "codes": ["sz300750", "sz002594", "sh601633", "sh600104", "sz002460", "sz002812"]},
    {"name": "光伏", "category": "概念板块", "codes": ["sh601012", "sz300274", "sz002459", "sh600438", "sh688599", "sz002129"]},
    {"name": "芯片", "category": "概念板块", "codes": ["sh688981", "sh688012", "sh688008", "sz300782", "sh603986", "sz002371"]},
    {"name": "上证指数", "category": "指数板块", "codes": ["sh000001"]},
    {"name": "深证成指", "category": "指数板块", "codes": ["sz399001"]},
    {"name": "沪深300", "category": "指数板块", "codes": ["sh000300"]},
    {"name": "创业板指", "category": "指数板块", "codes": ["sz399006"]},
]
STATIC_BOARD_CODE_MAP = {(group["category"], group["name"]): group["codes"] for group in STATIC_BOARD_GROUPS}
STATIC_BOARD_LEGACY_CODE_MAP = {group["name"]: group["codes"] for group in STATIC_BOARD_GROUPS}

# ── 实时加载 THS 板块映射 ──
_ths_map_cache: dict | None = None
_ths_map_mtime: float = 0


class _THSMemberTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            text = _clean_text(data)
            if text:
                self._cell.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _load_ths_map() -> dict:
    """从 JSON 缓存加载 THS 板块→股票映射（自动热更新）。"""
    global _ths_map_cache, _ths_map_mtime
    path = THS_SECTOR_MAP_PATH
    if path.exists():
        mtime = path.stat().st_mtime
        if _ths_map_cache is None or mtime > _ths_map_mtime:
            try:
                with open(path, encoding="utf-8") as f:
                    _ths_map_cache = json.load(f)
                _ths_map_mtime = mtime
                logger.info(f"THS板块映射已加载: {_ths_map_cache.get('total_sectors',0)}板块 {_ths_map_cache.get('total_stocks',0)}股票")
            except Exception as exc:
                logger.warning(f"THS板块映射加载失败: {exc}")
                _ths_map_cache = {"stock_to_sectors": {}, "sector_to_stocks": {}}
    return _ths_map_cache or {"stock_to_sectors": {}, "sector_to_stocks": {}}


def get_stock_sectors(code: str) -> List[str]:
    """获取股票所属的同花顺一级行业板块列表。"""
    symbol = code.replace("sh", "").replace("sz", "").replace("bj", "")
    exchange = _exchange_from_symbol(symbol)
    try:
        get_engine()
        db = SessionLocal()
        try:
            repo = StockBoardRepository(db)
            sectors = [
                board.name
                for board in repo.list_boards(category="行业板块")
                for member in repo.list_members(board=board)
                if member.symbol == symbol and member.exchange == exchange
            ]
            if sectors:
                return sectors
        finally:
            db.close()
    except Exception as exc:
        logger.warning("数据库股票板块查询失败: %s", exc)
    return _load_ths_map().get("stock_to_sectors", {}).get(symbol, [])


def get_sector_stocks(sector_name: str = "能源金属", category: str | None = None) -> List[Dict]:
    """获取板块成分股实时行情。行业板块优先使用同花顺板块表。"""
    normalized_category = _clean_text(category)
    if normalized_category == "行业板块":
        _ensure_ths_industry_boards()
        rows = _db_board_stocks(sector_name, category=normalized_category)
        if rows:
            return rows
        sector_stocks = _load_ths_map().get("sector_to_stocks", {}).get(sector_name, [])
        codes = [_stock_quote_code(symbol, _exchange_from_symbol(symbol)) for symbol in sector_stocks]
    elif normalized_category:
        codes = STATIC_BOARD_CODE_MAP.get((normalized_category, sector_name), [])
    else:
        rows = _db_board_stocks(sector_name, category=None)
        if rows:
            return rows
        sector_stocks = _load_ths_map().get("sector_to_stocks", {}).get(sector_name, [])
        if sector_stocks:
            codes = [_stock_quote_code(symbol, _exchange_from_symbol(symbol)) for symbol in sector_stocks]
        else:
            codes = STATIC_BOARD_LEGACY_CODE_MAP.get(sector_name, [])

    quotes = get_realtime_quotes(codes)
    for quote in quotes:
        quote["sectors"] = [sector_name]
    return quotes


def _static_sector_rankings(requested_categories: list[str]) -> list[dict]:
    """板块排行后备。行业板块只返回同花顺短行业名。"""
    groups = []
    for category in requested_categories:
        if category == "行业板块":
            sector_stocks_map = _load_ths_map().get("sector_to_stocks", {})
            for name in THS_INDUSTRY_SECTORS:
                codes = sector_stocks_map.get(name, [])
                groups.append({
                    "name": name,
                    "category": "行业板块",
                    "codes": [_stock_quote_code(symbol, _exchange_from_symbol(symbol)) for symbol in codes],
                })
        else:
            groups.extend(group for group in STATIC_BOARD_GROUPS if group["category"] == category)

    all_codes = sorted({code for group in groups for code in group["codes"]})
    quotes_by_code = _quotes_for_codes(all_codes)

    rows = []
    for group in groups:
        quotes = [quotes_by_code[code] for code in group["codes"] if code in quotes_by_code]
        leader = max(quotes, key=lambda item: item.get("change_pct", 0), default=None) if quotes else None
        change_pct = (
            sum(item.get("change_pct", 0) for item in quotes) / len(quotes)
            if quotes else 0
        )
        rows.append({
            "name": group["name"],
            "category": group["category"],
            "change_pct": round(change_pct, 2),
            "up_count": sum(1 for item in quotes if item.get("change_pct", 0) > 0),
            "down_count": sum(1 for item in quotes if item.get("change_pct", 0) < 0),
            "stock_count": len(quotes),
            "amount": round(sum(item.get("amount", 0) for item in quotes), 2),
            "volume": sum(item.get("volume", 0) for item in quotes),
            "leader": leader,
        })
    return rows


def get_sector_rankings(categories: Optional[List[str]] = None) -> List[Dict]:
    """获取板块排行。行业板块优先使用同花顺短行业并写入数据库。"""
    requested_categories = [category for category in (categories or SECTOR_CATEGORY_ORDER) if category in SECTOR_CATEGORY_ORDER]
    if not requested_categories:
        requested_categories = SECTOR_CATEGORY_ORDER

    rows: list[dict] = []
    static_categories = list(requested_categories)
    if "行业板块" in requested_categories:
        ths_rows = _ensure_ths_industry_boards()
        if ths_rows:
            rows.extend(ths_rows)
            static_categories = [category for category in static_categories if category != "行业板块"]

    rows.extend(_static_sector_rankings(static_categories))

    grouped_rows: list[dict] = []
    for category in requested_categories:
        category_rows = [row for row in rows if row["category"] == category]
        grouped_rows.extend(sorted(category_rows, key=lambda item: item["change_pct"], reverse=True))
    return grouped_rows


def _stock_quote_code(symbol: str, exchange: str) -> str:
    prefix = "sh" if exchange == "SSE" else "bj" if exchange == "BSE" else "sz"
    return f"{prefix}{symbol}"


def _exchange_from_symbol(symbol: str) -> str:
    if symbol.startswith(("43", "83", "87", "88", "92")):
        return "BSE"
    if symbol.startswith(("5", "6", "9")):
        return "SSE"
    return "SZSE"


def _empty_quote(code: str, name: str, sectors: list[str] | None = None) -> Dict:
    return {
        "code": code,
        "name": name,
        "price": 0,
        "change": 0,
        "change_pct": 0,
        "open": 0,
        "high": 0,
        "low": 0,
        "volume": 0,
        "amount": 0,
        "pe": 0,
        "pb": 0,
        "turnover": 0,
        "bid1_price": 0,
        "bid1_vol": 0,
        "ask1_price": 0,
        "ask1_vol": 0,
        "prev_close": 0,
        "sectors": sectors or [],
    }


def _quotes_for_codes(codes: list[str]) -> Dict[str, Dict]:
    chunks = [codes[start:start + 30] for start in range(0, len(codes), 30)]
    quotes = []
    if len(chunks) <= 1:
        for chunk in chunks:
            quotes.extend(get_realtime_quotes(chunk))
    else:
        with ThreadPoolExecutor(max_workers=min(6, len(chunks))) as executor:
            for chunk_quotes in executor.map(get_realtime_quotes, chunks):
                quotes.extend(chunk_quotes)
    return {quote["code"]: quote for quote in quotes}


def _records_from_frame(frame) -> list[dict]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [row for row in frame if isinstance(row, dict)]
    if isinstance(frame, dict):
        return [frame]
    to_dict = getattr(frame, "to_dict", None)
    if callable(to_dict):
        try:
            return list(to_dict(orient="records"))
        except TypeError:
            records = to_dict()
            return records if isinstance(records, list) else []
    return []


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").replace("\xa0", " ").strip()
    return "" if text.lower() in {"", "none", "nan", "nat", "--", "-"} else text


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if value != value else float(value)
    text = _clean_text(value)
    if not text:
        return None
    text = text.replace(",", "").replace("%", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _to_int(value) -> int:
    number = _to_float(value)
    return int(number) if number is not None else 0


def _import_akshare():
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        return import_module("akshare")


def _fetch_ths_industry_code_map(ak) -> dict[str, str]:
    names = ak.stock_board_industry_name_ths()
    return {
        _clean_text(row.get("name")): _clean_text(row.get("code"))
        for row in _records_from_frame(names)
        if _clean_text(row.get("name")) and _clean_text(row.get("code"))
    }


def _member_from_row(row: dict) -> dict | None:
    raw_symbol = _clean_text(row.get("代码") or row.get("code"))
    stock_name = _clean_text(row.get("名称") or row.get("name"))
    symbol_match = re.search(r"\d{1,6}", raw_symbol)
    if not symbol_match or not stock_name:
        return None
    symbol = symbol_match.group(0).zfill(6)
    return {
        "symbol": symbol,
        "exchange": _exchange_from_symbol(symbol),
        "name": stock_name,
    }


def _fetch_ths_industry_members(ak, name: str) -> list[dict]:
    provider_code = _fetch_ths_industry_code_map(ak).get(name)
    if not provider_code:
        return []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        ),
        "Referer": "http://q.10jqka.com.cn/thshy/",
    }
    first_url = f"http://q.10jqka.com.cn/thshy/detail/code/{provider_code}/"
    first_html = _request(first_url, headers=headers, timeout=15, encoding="gbk")
    page_count_match = re.search(r'class=["\']page_info["\'][^>]*>\s*\d+\s*/\s*(\d+)', first_html)
    page_count = int(page_count_match.group(1)) if page_count_match else 1
    html_pages = [first_html]
    for page in range(2, page_count + 1):
        page_url = f"http://q.10jqka.com.cn/thshy/detail/code/{provider_code}/page/{page}/"
        html_pages.append(_request(page_url, headers=headers, timeout=15, encoding="gbk"))

    members: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for html in html_pages:
        parser = _THSMemberTableParser()
        parser.feed(html)
        table_headers: list[str] | None = None
        for row in parser.rows:
            if "代码" in row and "名称" in row:
                table_headers = row
                continue
            if table_headers and len(row) >= len(table_headers):
                member = _member_from_row(dict(zip(table_headers, row, strict=False)))
                if member and (member["symbol"], member["exchange"]) not in seen:
                    members.append(member)
                    seen.add((member["symbol"], member["exchange"]))
    return members


def _stock_board_to_ranking(board) -> dict:
    leader = None
    if board.leader_name:
        leader = {
            "code": "",
            "name": board.leader_name,
            "price": board.leader_price or 0,
            "change": 0,
            "change_pct": board.leader_change_pct or 0,
            "open": 0,
            "high": 0,
            "low": 0,
            "volume": 0,
            "amount": 0,
            "pe": 0,
            "pb": 0,
            "turnover": 0,
            "bid1_price": 0,
            "bid1_vol": 0,
            "ask1_price": 0,
            "ask1_vol": 0,
            "prev_close": 0,
        }
    return {
        "name": board.name,
        "category": board.category,
        "change_pct": round(board.change_pct or 0, 2),
        "up_count": board.up_count,
        "down_count": board.down_count,
        "stock_count": board.stock_count,
        "amount": board.amount,
        "volume": int(board.volume),
        "leader": leader,
        "fund_flow": board.net_inflow,
    }


def _db_stock_board_rankings(category: str) -> list[dict]:
    try:
        get_engine()
        db = SessionLocal()
        try:
            repo = StockBoardRepository(db)
            return [_stock_board_to_ranking(board) for board in repo.list_boards(category=category)]
        finally:
            db.close()
    except Exception as exc:
        logger.warning("数据库板块排行查询失败: %s", exc)
        return []


def _fetch_ths_industry_boards() -> list[dict]:
    ak = _import_akshare()
    summary = ak.stock_board_industry_summary_ths()
    try:
        code_by_name = _fetch_ths_industry_code_map(ak)
    except Exception as exc:
        logger.warning("同花顺行业板块代码表抓取失败: %s", exc)
        code_by_name = {}
    rows: list[dict] = []
    for row in _records_from_frame(summary):
        name = _clean_text(row.get("板块"))
        if not name:
            continue
        up_count = _to_int(row.get("上涨家数"))
        down_count = _to_int(row.get("下跌家数"))
        rows.append({
            "name": name,
            "category": "行业板块",
            "source": "akshare_ths",
            "provider_code": code_by_name.get(name),
            "change_pct": _to_float(row.get("涨跌幅")) or 0,
            "up_count": up_count,
            "down_count": down_count,
            "stock_count": up_count + down_count,
            "amount": (_to_float(row.get("总成交额")) or 0) * 100_000_000,
            "volume": (_to_float(row.get("总成交量")) or 0) * 10_000,
            "net_inflow": (_to_float(row.get("净流入")) or 0) * 100_000_000,
            "leader_name": _clean_text(row.get("领涨股")),
            "leader_price": _to_float(row.get("领涨股-最新价")),
            "leader_change_pct": _to_float(row.get("领涨股-涨跌幅")),
        })
    return rows


def _ensure_ths_industry_boards() -> list[dict]:
    existing = _db_stock_board_rankings("行业板块")
    if existing:
        return existing
    try:
        records = _fetch_ths_industry_boards()
        if not records:
            return []
        get_engine()
        db = SessionLocal()
        try:
            StockBoardRepository(db).upsert_boards(records)
            db.commit()
        finally:
            db.close()
        return _db_stock_board_rankings("行业板块")
    except Exception as exc:
        logger.warning("同花顺行业板块抓取失败，使用静态板块后备: %s", exc)
        return []


def _fetch_board_members(category: str, name: str) -> list[dict]:
    ak = _import_akshare()
    members: list[dict] = []
    if category == "行业板块":
        try:
            members = _fetch_ths_industry_members(ak, name)
        except Exception as exc:
            logger.warning("同花顺行业成分股抓取失败，尝试备用接口: %s", exc)

    function_name = "stock_board_industry_cons_em" if category == "行业板块" else "stock_board_concept_cons_em"
    if not hasattr(ak, function_name):
        return members
    try:
        frame = getattr(ak, function_name)(symbol=name)
    except Exception:
        if members:
            return members
        raise
    seen = {(member["symbol"], member["exchange"]) for member in members}
    for row in _records_from_frame(frame):
        member = _member_from_row(row)
        if member and (member["symbol"], member["exchange"]) not in seen:
            members.append(member)
            seen.add((member["symbol"], member["exchange"]))
    return members


def _sync_stock_industries_from_board_members(db, repo: StockBoardRepository) -> int:
    industry_by_symbol: dict[tuple[str, str, str], str] = {}
    for board in repo.list_boards(category="行业板块"):
        for member in repo.list_members(board=board):
            industry_by_symbol[(member.symbol, member.exchange, "A_SHARE")] = board.name
    return StockRepository(db).update_industries(industry_by_symbol)


def sync_ths_industry_boards(*, include_members: bool = True, limit: int | None = None) -> dict:
    records = _fetch_ths_industry_boards()
    if limit is not None:
        records = records[:limit]
    if not records:
        return {
            "boards_read": 0,
            "boards_written": 0,
            "boards_with_members": 0,
            "members_written": 0,
            "stocks_updated": 0,
            "failed_boards": [],
        }

    get_engine()
    db = SessionLocal()
    failed_boards: list[dict] = []
    boards_with_members = 0
    members_written = 0
    try:
        repo = StockBoardRepository(db)
        boards_written = repo.upsert_boards(records)
        db.commit()

        if include_members:
            for record in records:
                board_name = record["name"]
                board = repo.get_board(name=board_name, category="行业板块")
                if board is None:
                    continue
                try:
                    members = _fetch_board_members("行业板块", board_name)
                except Exception as exc:
                    failed_boards.append({"name": board_name, "error": str(exc)})
                    db.rollback()
                    continue
                if not members:
                    failed_boards.append({"name": board_name, "error": "empty members"})
                    continue
                members_written += repo.replace_members(board=board, members=members, source="akshare")
                boards_with_members += 1
                db.commit()

        stocks_updated = _sync_stock_industries_from_board_members(db, repo)
        db.commit()
        return {
            "boards_read": len(records),
            "boards_written": boards_written,
            "boards_with_members": boards_with_members,
            "members_written": members_written,
            "stocks_updated": stocks_updated,
            "failed_boards": failed_boards[:20],
        }
    finally:
        db.close()


def _db_board_stocks(sector_name: str, *, category: str | None) -> list[dict]:
    try:
        get_engine()
        db = SessionLocal()
        try:
            repo = StockBoardRepository(db)
            board = repo.get_board(name=sector_name, category=category)
            if board is None:
                return []
            members = repo.list_members(board=board)
            if not members:
                try:
                    fetched_members = _fetch_board_members(category or board.category, sector_name)
                except Exception as exc:
                    logger.warning("板块成分股抓取失败: %s", exc)
                    fetched_members = []
                if fetched_members:
                    repo.replace_members(board=board, members=fetched_members, source="akshare")
                    db.commit()
                    members = repo.list_members(board=board)
            if not members:
                return []
            codes = [_stock_quote_code(member.symbol, member.exchange) for member in members]
            quotes_by_code = _quotes_for_codes(codes)
            rows: list[dict] = []
            for member, code in zip(members, codes, strict=False):
                row = quotes_by_code.get(code, _empty_quote(code, member.name))
                row["sectors"] = [sector_name]
                rows.append(row)
            return rows
        finally:
            db.close()
    except Exception as exc:
        logger.warning("数据库板块成分股查询失败: %s", exc)
        return []


def _db_industry_groups() -> list[dict]:
    try:
        get_engine()
        db = SessionLocal()
        try:
            repo = StockRepository(db)
            groups = repo.list_industry_groups(market="A_SHARE", common_only=True)
            group_samples: list[tuple[str, int, list[str]]] = []
            for industry, stock_count in groups[:24]:
                stocks = repo.list_stocks_by_industry(
                    industry=industry,
                    market="A_SHARE",
                    status="LISTED",
                    limit=4,
                    common_only=True,
                )
                group_samples.append((
                    industry,
                    stock_count,
                    [_stock_quote_code(stock.symbol, stock.exchange) for stock in stocks],
                ))
            for industry, stock_count in groups[24:]:
                group_samples.append((industry, stock_count, []))

            all_codes = sorted({code for _, _, codes in group_samples for code in codes})
            quotes_by_code = _quotes_for_codes(all_codes)

            rows: list[dict] = []
            for industry, stock_count, codes in group_samples:
                quotes = [quotes_by_code[code] for code in codes if code in quotes_by_code]
                leader = max(quotes, key=lambda item: item.get("change_pct", 0), default=None)
                change_pct = (
                    sum(item.get("change_pct", 0) for item in quotes) / len(quotes)
                    if quotes else 0
                )
                rows.append({
                    "name": industry,
                    "category": "行业板块",
                    "change_pct": round(change_pct, 2),
                    "up_count": sum(1 for item in quotes if item.get("change_pct", 0) > 0),
                    "down_count": sum(1 for item in quotes if item.get("change_pct", 0) < 0),
                    "stock_count": stock_count,
                    "amount": round(sum(item.get("amount", 0) for item in quotes), 2),
                    "volume": sum(item.get("volume", 0) for item in quotes),
                    "leader": leader,
                })
            return sorted(rows, key=lambda item: item["change_pct"], reverse=True)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("数据库行业板块聚合失败，使用静态板块后备: %s", exc)
        return []


def _db_sector_stocks(industry: str) -> list[dict]:
    try:
        get_engine()
        db = SessionLocal()
        try:
            repo = StockRepository(db)
            stocks = repo.list_stocks_by_industry(
                industry=industry,
                market="A_SHARE",
                status="LISTED",
                limit=None,
                common_only=True,
            )
            if not stocks:
                return []

            codes = [_stock_quote_code(stock.symbol, stock.exchange) for stock in stocks]
            quotes_by_code = _quotes_for_codes(codes)
            rows: list[dict] = []
            for stock, code in zip(stocks, codes, strict=False):
                row = quotes_by_code.get(code, _empty_quote(code, stock.name))
                row["sectors"] = [industry]
                rows.append(row)
            return rows
        finally:
            db.close()
    except Exception as exc:
        logger.warning("数据库行业成分股查询失败，使用静态板块后备: %s", exc)
        return []


def _request(url: str, headers: dict = None, timeout: int = 10, encoding: str = "utf-8") -> str:
    """发送HTTP请求，不走系统代理"""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(encoding, errors="ignore")


def get_realtime_quotes(codes: List[str]) -> List[Dict]:
    """获取实时行情（腾讯API直连）

    Args:
        codes: 股票代码列表，如 ['sh600900', 'sz000858']

    Returns:
        [
            {
                'code': 'sh600900',
                'name': '长江电力',
                'price': 26.50,
                'change': -0.15,
                'change_pct': -0.56,
                'open': 26.65,
                'high': 26.70,
                'low': 26.40,
                'volume': 1234567,
                'amount': 32500000,
                'pe': 18.5,
                'pb': 3.2,
                'turnover': 0.05,
                'bid1_price': 26.49,
                'bid1_vol': 100,
                'ask1_price': 26.50,
                'ask1_vol': 200,
            }
        ]
    """
    if not codes:
        return []

    query = ",".join(codes)
    url = f"https://qt.gtimg.cn/q={query}"

    try:
        text = _request(url, encoding="gbk")
    except Exception as e:
        logger.error(f"实时行情请求失败: {e}")
        return []

    results = []
    for line in text.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue

        var_name, raw_val = line.split("=", 1)
        raw_val = raw_val.strip('"')

        # 提取股票代码
        code_match = re.search(r'v_([a-z]{2}\d{6})', var_name)
        if not code_match:
            continue
        code = code_match.group(1)

        fields = raw_val.split("~")
        if len(fields) < 48:
            continue

        try:
            result = {
                "code": code,
                "name": fields[1],
                "price": float(fields[3]) if fields[3] else 0,
                "change": float(fields[31]) if fields[31] else 0,
                "change_pct": float(fields[32]) if fields[32] else 0,
                "open": float(fields[5]) if fields[5] else 0,
                "high": float(fields[33]) if fields[33] else 0,
                "low": float(fields[34]) if fields[34] else 0,
                "volume": int(float(fields[6])) if fields[6] else 0,
                "amount": float(fields[37]) if fields[37] else 0,
                "pe": float(fields[39]) if fields[39] else 0,
                "pb": float(fields[46]) if fields[46] else 0,
                "turnover": float(fields[38]) if fields[38] else 0,
                "bid1_price": float(fields[9]) if fields[9] else 0,
                "bid1_vol": int(float(fields[10])) if fields[10] else 0,
                "ask1_price": float(fields[19]) if fields[19] else 0,
                "ask1_vol": int(float(fields[20])) if fields[20] else 0,
                "prev_close": float(fields[4]) if fields[4] else 0,
            }
            results.append(result)
        except (ValueError, IndexError) as e:
            logger.warning(f"解析 {code} 失败: {e}")
            continue

    return results


def get_history_kline(
    code: str,
    period: str = "day",
    count: int = 100,
    adjust: str = "qfq",
) -> List[Dict]:
    """获取历史K线（腾讯API直连）

    Args:
        code: 股票代码，如 'sh600900'
        period: day/week/month
        count: 返回条数
        adjust: qfq(前复权)/hfq(后复权)/空(不复权)

    Returns:
        [
            {
                'date': '2026-06-12',
                'open': 27.77,
                'high': 28.28,
                'close': 28.29,
                'low': 27.67,
                'volume': 1494245,
            }
        ]
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    # 回溯足够天数
    if period == "day":
        start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y-%m-%d")
    elif period == "week":
        start_date = (datetime.now() - timedelta(weeks=count * 2)).strftime("%Y-%m-%d")
    else:
        start_date = (datetime.now() - timedelta(days=count * 60)).strftime("%Y-%m-%d")

    param = f"{code},{period},{start_date},{end_date},{count},{adjust}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={param}"

    try:
        text = _request(url, encoding="gbk")
        data = json.loads(text)
    except Exception as e:
        logger.error(f"K线请求失败: {e}")
        return []

    # 解析响应
    key_map = {"day": "qfqday", "week": "qfqweek", "month": "qfqmonth"}
    period_key = key_map.get(period, "qfqday")

    results = []
    for stock_code, stock_data in data.get("data", {}).items():
        klines = stock_data.get(period_key, [])
        for k in klines[-count:]:
            try:
                # 返回格式: [date, open, high, close, low, volume]
                results.append({
                    "date": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "close": float(k[3]),
                    "low": float(k[4]),
                    "volume": int(float(k[5])) if len(k) > 5 else 0,
                })
            except (ValueError, IndexError) as e:
                logger.warning(f"解析K线数据失败: {e}")
                continue

    return results


def _classify_news(title: str, summary: str) -> str:
    """简单的基于关键词的新闻分类"""
    text = (title + " " + summary).lower()
    if any(k in text for k in ["央行", "降准", "降息", "政策", "监管", "国务院", "证监会", "财政", "货币", "利率"]):
        return "政策"
    if any(k in text for k in ["分红", "业绩", "公告", "减持", "增持", "回购", "营收", "净利润", "合同", "中标", "募资"]):
        return "公司"
    if any(k in text for k in ["板块", "行业", "光伏", "新能源", "芯片", "人工智能", "汽车", "医药", "消费", "半导体", "锂电"]):
        return "行业"
    return "市场"


def get_news(keyword: str = "A股", limit: int = 20, page: int = 1) -> List[Dict]:
    """获取新浪财经新闻（API直连）

    Args:
        keyword: 搜索关键词
        limit: 返回条数
        page: 页码

    Returns:
        [
            {
                'title': '新闻标题',
                'url': 'https://...',
                'summary': '摘要...',
                'source': '新浪财经',
                'created_at': '2026-06-22 10:30:00',
            }
        ]
    """
    params = urllib.parse.urlencode({
        "pageid": "153",
        "lid": "2516",
        "k": keyword,
        "num": str(min(limit, 50)),
        "page": str(page),
    })
    url = f"https://feed.mix.sina.com.cn/api/roll/get?{params}"

    try:
        text = _request(url)
        data = json.loads(text)
    except Exception as e:
        logger.error(f"新闻请求失败: {e}")
        return []

    items = data.get("result", {}).get("data", [])
    results = []

    for item in items[:limit]:
        try:
            created_ts = int(item.get("ctime", 0))
            created_at = (
                datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
                if created_ts
                else ""
            )

            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": item.get("summary", "")[:200],
                "source": item.get("media_name", "新浪"),
                "created_at": created_at,
                "category": _classify_news(
                    item.get("title", ""),
                    item.get("summary", ""),
                ),
            })
        except Exception as e:
            logger.warning(f"解析新闻失败: {e}")
            continue

    return results


def search_stock(keyword: str, limit: int = 10) -> List[Dict]:
    """搜索股票（腾讯API直连）

    Args:
        keyword: 搜索关键词（名称或代码）
        limit: 返回条数

    Returns:
        [
            {
                'code': 'sh600900',
                'name': '长江电力',
                'market': 'sh',
            }
        ]
    """
    params = urllib.parse.urlencode({"q": keyword, "t": "gp"})
    url = f"https://smartbox.gtimg.cn/s3/?v=2&q={params}&t=gp"

    try:
        text = _request(url, encoding="gbk")
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return []

    # 解析返回格式: v_hint="gp~sh~600900~长江电力~..."
    match = re.search(r'v_hint="([^"]*)"', text)
    if not match:
        return []

    raw = match.group(1)
    results = []
    for item in raw.split("^"):
        parts = item.split("~")
        if len(parts) >= 4:
            results.append({
                "code": f"{parts[0]}{parts[1]}",
                "name": parts[3],
                "market": parts[0],
            })

    return results[:limit]


def get_index_quotes() -> List[Dict]:
    """获取大盘指数实时行情

    Returns:
        [
            {
                'code': 'sh000001',
                'name': '上证指数',
                'price': 3250.50,
                'change': 15.30,
                'change_pct': 0.47,
            }
        ]
    """
    index_codes = ["sh000001", "sz399001", "sh000300", "sz399006", "sh000688", "sh000905", "sh000852"]
    return get_realtime_quotes(index_codes)


def get_sector_constituents(sector_name: str) -> List[Dict]:
    """获取板块成分股实时行情

    Args:
        sector_name: 板块名称，如 '银行'、'人工智能'

    Returns:
        成分股实时行情列表，包含股票所属板块信息
    """
    return get_sector_stocks(sector_name)


if __name__ == "__main__":
    """独立测试"""
    print("=" * 60)
    print("市场数据服务 - 独立测试")
    print("=" * 60)

    # 1. 大盘指数
    print("\n【1. 大盘指数】")
    for idx in get_index_quotes()[:4]:
        arrow = "↑" if idx["change"] >= 0 else "↓"
        print(f"  {idx['name']}: {idx['price']:.2f} {arrow}{idx['change']:+.2f} ({idx['change_pct']:+.2f}%)")

    # 2. 股票搜索
    print("\n【2. 股票搜索 '长江电力'】")
    for s in search_stock("长江电力", 3):
        print(f"  {s['name']} ({s['code']})")

    # 3. 实时行情
    print("\n【3. 实时行情 sh600900】")
    quotes = get_realtime_quotes(["sh600900"])
    if quotes:
        q = quotes[0]
        print(f"  {q['name']}: {q['price']:.2f} ({q['change_pct']:+.2f}%) PE={q['pe']:.1f}")

    # 4. K线
    print("\n【4. 历史K线 sh600900 近5日】")
    klines = get_history_kline("sh600900", period="day", count=5)
    for k in klines:
        print(f"  {k['date']} O={k['open']:.2f} H={k['high']:.2f} C={k['close']:.2f} L={k['low']:.2f}")

    # 5. 新闻
    print("\n【5. 新浪新闻 '电力'】")
    news = get_news(keyword="电力", limit=5)
    for n in news[:5]:
        print(f"  {n['title'][:50]}  ({n['created_at']})")

    # 6. 板块
    print("\n【6. 电力板块】")
    for s in get_sector_stocks("电力")[:5]:
        arrow = "↑" if s["change"] >= 0 else "↓"
        print(f"  {s['name']}: {s['price']:.2f} {arrow}{s['change_pct']:+.2f}%")
