"""板块服务 - 板块成分股、排行、同花顺行业板块同步"""

import json
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Dict, Optional

from backend.app.db.session import SessionLocal, get_engine
from backend.app.repositories.stock_boards import StockBoardRepository
from backend.app.repositories.stocks import StockRepository

from backend.app.services import quote_service as _qs

logger = logging.getLogger(__name__)

THS_SECTOR_MAP_PATH = Path(__file__).resolve().parents[3] / "data" / "mcp_cache" / "ths_sector_map.json"
SECTOR_CATEGORY_ORDER = ["行业板块", "概念板块", "指数板块"]


def _get_ths_industry_sectors() -> list[str]:
    """从同花顺 API 获取全部 90 个行业板块名称"""
    try:
        ak = _qs._import_akshare()
        names = ak.stock_board_industry_name_ths()
        return sorted(n['name'] for _, n in names.iterrows())
    except Exception:
        logger.warning("获取同花顺行业板块名称失败，使用空列表")
        return []


# ── 静态板块数据 ──
_static_boards_path = Path(__file__).resolve().parent / "data" / "static_boards.json"
if _static_boards_path.exists():
    with open(_static_boards_path, encoding="utf-8") as _f:
        STATIC_BOARD_GROUPS: list[dict] = json.load(_f)
else:
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
STATIC_BOARD_CODE_MAP = {(g["category"], g["name"]): g["codes"] for g in STATIC_BOARD_GROUPS}
STATIC_BOARD_LEGACY_CODE_MAP = {g["name"]: g["codes"] for g in STATIC_BOARD_GROUPS}

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
            text = _qs._clean_text(data)
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


# ── THS 板块映射 ──

def _load_ths_map() -> dict:
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


def _fetch_ths_industry_code_map(ak) -> dict[str, str]:
    names = ak.stock_board_industry_name_ths()
    return {
        _qs._clean_text(row.get("name")): _qs._clean_text(row.get("code"))
        for row in _qs._records_from_frame(names)
        if _qs._clean_text(row.get("name")) and _qs._clean_text(row.get("code"))
    }


def _fetch_ths_industry_members(ak, name: str) -> list[dict]:
    provider_code = _fetch_ths_industry_code_map(ak).get(name)
    if not provider_code:
        return []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://q.10jqka.com.cn/thshy/",
    }
    first_url = f"http://q.10jqka.com.cn/thshy/detail/code/{provider_code}/"
    first_html = _qs._request(first_url, headers=headers, timeout=15, encoding="gbk")
    m = re.search(r'class=["\']page_info["\'][^>]*>\s*\d+\s*/\s*(\d+)', first_html)
    page_count = int(m.group(1)) if m else 1
    html_pages = [first_html]
    for page in range(2, page_count + 1):
        html_pages.append(_qs._request(
            f"http://q.10jqka.com.cn/thshy/detail/code/{provider_code}/page/{page}/",
            headers=headers, timeout=15, encoding="gbk",
        ))
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
                member = _qs._member_from_row(dict(zip(table_headers, row, strict=False)))
                if member and (member["symbol"], member["exchange"]) not in seen:
                    members.append(member)
                    seen.add((member["symbol"], member["exchange"]))
    return members


# ── 数据库操作辅助 ──

def _quotes_for_codes(codes: list[str]) -> Dict[str, Dict]:
    chunks = [codes[start:start + 30] for start in range(0, len(codes), 30)]
    quotes = []
    if len(chunks) <= 1:
        for chunk in chunks:
            quotes.extend(_qs.get_realtime_quotes(chunk))
    else:
        with ThreadPoolExecutor(max_workers=min(6, len(chunks))) as executor:
            for chunk_quotes in executor.map(_qs.get_realtime_quotes, chunks):
                quotes.extend(chunk_quotes)
    return {quote["code"]: quote for quote in quotes}


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
                    fetched = _fetch_board_members(category or board.category, sector_name)
                except Exception as exc:
                    logger.warning(f"板块成分股抓取失败: {exc}")
                    fetched = []
                if fetched:
                    repo.replace_members(board=board, members=fetched, source="akshare")
                    db.commit()
                    members = repo.list_members(board=board)
            if not members:
                return []
            codes = [_qs._stock_quote_code(m.symbol, m.exchange) for m in members]
            quotes_by_code = _quotes_for_codes(codes)
            return [
                {**quotes_by_code.get(code, _qs._empty_quote(code, m.name)), "sectors": [sector_name]}
                for m, code in zip(members, codes, strict=False)
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"数据库板块成分股查询失败: {exc}")
        return []


def _stock_board_to_ranking(board) -> dict:
    leader = None
    if board.leader_name:
        leader = {
            "code": "", "name": board.leader_name,
            "price": board.leader_price or 0, "change": 0,
            "change_pct": board.leader_change_pct or 0,
            "open": 0, "high": 0, "low": 0, "volume": 0,
            "amount": 0, "pe": 0, "pb": 0, "turnover": 0,
            "bid1_price": 0, "bid1_vol": 0, "ask1_price": 0,
            "ask1_vol": 0, "prev_close": 0,
        }
    return {
        "name": board.name, "category": board.category,
        "change_pct": round(board.change_pct or 0, 2),
        "up_count": board.up_count, "down_count": board.down_count,
        "stock_count": board.stock_count, "amount": board.amount,
        "volume": int(board.volume), "leader": leader, "fund_flow": board.net_inflow,
    }


def _db_stock_board_rankings(category: str) -> list[dict]:
    try:
        get_engine()
        db = SessionLocal()
        try:
            return [_stock_board_to_ranking(b) for b in StockBoardRepository(db).list_boards(category=category)]
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"数据库板块排行查询失败: {exc}")
        return []


def _fetch_ths_industry_boards() -> list[dict]:
    ak = _qs._import_akshare()
    summary = ak.stock_board_industry_summary_ths()
    try:
        code_by_name = _fetch_ths_industry_code_map(ak)
    except Exception as exc:
        logger.warning(f"同花顺行业板块代码表抓取失败: {exc}")
        code_by_name = {}
    rows = []
    for row in _qs._records_from_frame(summary):
        name = _qs._clean_text(row.get("板块"))
        if not name:
            continue
        up_count = _qs._to_int(row.get("上涨家数"))
        down_count = _qs._to_int(row.get("下跌家数"))
        rows.append({
            "name": name, "category": "行业板块", "source": "akshare_ths",
            "provider_code": code_by_name.get(name),
            "change_pct": _qs._to_float(row.get("涨跌幅")) or 0,
            "up_count": up_count, "down_count": down_count,
            "stock_count": up_count + down_count,
            "amount": (_qs._to_float(row.get("总成交额")) or 0) * 100_000_000,
            "volume": (_qs._to_float(row.get("总成交量")) or 0) * 10_000,
            "net_inflow": (_qs._to_float(row.get("净流入")) or 0) * 100_000_000,
            "leader_name": _qs._clean_text(row.get("领涨股")),
            "leader_price": _qs._to_float(row.get("领涨股-最新价")),
            "leader_change_pct": _qs._to_float(row.get("领涨股-涨跌幅")),
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
        logger.warning(f"同花顺行业板块抓取失败: {exc}")
        return []


def _static_sector_rankings(requested_categories: list[str]) -> list[dict]:
    groups = []
    for category in requested_categories:
        if category == "行业板块":
            sector_stocks_map = _load_ths_map().get("sector_to_stocks", {})
            for name in _get_ths_industry_sectors():
                codes = sector_stocks_map.get(name, [])
                groups.append({
                    "name": name, "category": "行业板块",
                    "codes": [_qs._stock_quote_code(s, _qs._exchange_from_symbol(s)) for s in codes],
                })
        else:
            groups.extend(g for g in STATIC_BOARD_GROUPS if g["category"] == category)
    all_codes = sorted({code for g in groups for code in g["codes"]})
    quotes_by_code = _quotes_for_codes(all_codes)
    rows = []
    for g in groups:
        quotes = [quotes_by_code[c] for c in g["codes"] if c in quotes_by_code]
        leader = max(quotes, key=lambda x: x.get("change_pct", 0), default=None) if quotes else None
        change_pct = sum(x.get("change_pct", 0) for x in quotes) / len(quotes) if quotes else 0
        rows.append({
            "name": g["name"], "category": g["category"],
            "change_pct": round(change_pct, 2),
            "up_count": sum(1 for x in quotes if x.get("change_pct", 0) > 0),
            "down_count": sum(1 for x in quotes if x.get("change_pct", 0) < 0),
            "stock_count": len(quotes),
            "amount": round(sum(x.get("amount", 0) for x in quotes), 2),
            "volume": sum(x.get("volume", 0) for x in quotes),
            "leader": leader,
        })
    return rows


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
        cat_rows = sorted([r for r in rows if r["category"] == cat], key=lambda x: x["change_pct"], reverse=True)
        grouped.extend(cat_rows)
    return grouped


# ── 板块成分股 ──

def _fetch_board_members(category: str, name: str) -> list[dict]:
    ak = _qs._import_akshare()
    members: list[dict] = []
    if category == "行业板块":
        try:
            members = _fetch_ths_industry_members(ak, name)
        except Exception as exc:
            logger.warning(f"同花顺行业成分股抓取失败: {exc}")
    func = "stock_board_industry_cons_em" if category == "行业板块" else "stock_board_concept_cons_em"
    if not hasattr(ak, func):
        return members
    try:
        frame = getattr(ak, func)(symbol=name)
    except Exception:
        if members:
            return members
        raise
    seen = {(m["symbol"], m["exchange"]) for m in members}
    for row in _qs._records_from_frame(frame):
        member = _qs._member_from_row(row)
        if member and (member["symbol"], member["exchange"]) not in seen:
            members.append(member)
            seen.add((member["symbol"], member["exchange"]))
    return members


def get_stock_sectors(code: str) -> List[str]:
    """获取股票所属的同花顺一级行业板块列表"""
    symbol = code.replace("sh", "").replace("sz", "").replace("bj", "")
    exchange = _qs._exchange_from_symbol(symbol)
    try:
        get_engine()
        db = SessionLocal()
        try:
            repo = StockBoardRepository(db)
            sectors = [
                b.name for b in repo.list_boards(category="行业板块")
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
    normalized_category = _qs._clean_text(category)
    if normalized_category == "行业板块":
        _ensure_ths_industry_boards()
        rows = _db_board_stocks(sector_name, category=normalized_category)
        if rows:
            return rows
        stocks = _load_ths_map().get("sector_to_stocks", {}).get(sector_name, [])
        codes = [_qs._stock_quote_code(s, _qs._exchange_from_symbol(s)) for s in stocks]
    elif normalized_category:
        codes = STATIC_BOARD_CODE_MAP.get((normalized_category, sector_name), [])
    else:
        rows = _db_board_stocks(sector_name, category=None)
        if rows:
            return rows
        stocks = _load_ths_map().get("sector_to_stocks", {}).get(sector_name, [])
        if stocks:
            codes = [_qs._stock_quote_code(s, _qs._exchange_from_symbol(s)) for s in stocks]
        else:
            codes = STATIC_BOARD_LEGACY_CODE_MAP.get(sector_name, [])
    quotes = _qs.get_realtime_quotes(codes)
    for q in quotes:
        q["sectors"] = [sector_name]
    return quotes


def get_sector_constituents(sector_name: str) -> List[Dict]:
    """获取板块成分股实时行情"""
    return get_sector_stocks(sector_name)


# ── 行业板块数据库聚合 ──

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
                    industry=industry, market="A_SHARE", status="LISTED", limit=4, common_only=True,
                )
                group_samples.append((industry, stock_count, [_qs._stock_quote_code(s.symbol, s.exchange) for s in stocks]))
            for industry, stock_count in groups[24:]:
                group_samples.append((industry, stock_count, []))
            all_codes = sorted({c for _, _, cs in group_samples for c in cs})
            quotes_by_code = _quotes_for_codes(all_codes)
            rows = []
            for industry, stock_count, codes in group_samples:
                quotes = [quotes_by_code[c] for c in codes if c in quotes_by_code]
                leader = max(quotes, key=lambda x: x.get("change_pct", 0), default=None)
                change_pct = sum(x.get("change_pct", 0) for x in quotes) / len(quotes) if quotes else 0
                rows.append({
                    "name": industry, "category": "行业板块",
                    "change_pct": round(change_pct, 2),
                    "up_count": sum(1 for x in quotes if x.get("change_pct", 0) > 0),
                    "down_count": sum(1 for x in quotes if x.get("change_pct", 0) < 0),
                    "stock_count": stock_count,
                    "amount": round(sum(x.get("amount", 0) for x in quotes), 2),
                    "volume": sum(x.get("volume", 0) for x in quotes),
                    "leader": leader,
                })
            return sorted(rows, key=lambda x: x["change_pct"], reverse=True)
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"数据库行业板块聚合失败: {exc}")
        return []


def _db_sector_stocks(industry: str) -> list[dict]:
    try:
        get_engine()
        db = SessionLocal()
        try:
            stocks = StockRepository(db).list_stocks_by_industry(
                industry=industry, market="A_SHARE", status="LISTED", limit=None, common_only=True,
            )
            if not stocks:
                return []
            codes = [_qs._stock_quote_code(s.symbol, s.exchange) for s in stocks]
            quotes_by_code = _quotes_for_codes(codes)
            return [
                {**quotes_by_code.get(c, _qs._empty_quote(c, s.name)), "sectors": [industry]}
                for s, c in zip(stocks, codes, strict=False)
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"数据库行业成分股查询失败: {exc}")
        return []


# ── THS 行业板块同步 ──

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
        return {"boards_read": 0, "boards_written": 0, "boards_with_members": 0,
                "members_written": 0, "stocks_updated": 0, "failed_boards": []}
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
        return {"boards_read": len(records), "boards_written": boards_written,
                "boards_with_members": boards_with_members, "members_written": members_written,
                "stocks_updated": stocks_updated, "failed_boards": failed_boards[:20]}
    finally:
        db.close()
