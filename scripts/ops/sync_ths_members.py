"""
同步同花顺板块成分股 — 超稳健版
从 DB 取 provider_code，直接爬 THS 网站，不依赖 akshare THS API
"""
import sys
import os
import re
import time
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from html.parser import HTMLParser
from typing import Optional

os.environ.setdefault("TQDM_DISABLE", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from apps.api.db.session import SessionLocal, get_engine
from apps.api.repositories.stock_boards import StockBoardRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_ths_members")


class _THSMemberTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_table = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_cell = False
        self._skip_tag = False
        self._table_tag_count = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table_tag_count += 1
            # THS uses class="m-table m-page-list" for the member table
            for k, v in attrs:
                if k == "class" and "m-table" in (v or ""):
                    self._in_table = True
        if self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []
        if self._in_table and tag in ("br",):
            self._current_cell.append("\n")
            self._skip_tag = True
        if self._in_table and tag == "a":
            self._skip_tag = True

    def handle_endtag(self, tag):
        if tag == "table":
            self._table_tag_count -= 1
            if self._in_table:
                self._in_table = False
                if self._current_row:
                    self.rows.append(self._current_row)
                    self._current_row = []
        if self._in_table and tag in ("td", "th"):
            self._in_cell = False
            text = "".join(self._current_cell).strip()
            self._current_row.append(text)
        if tag == "tr":
            if self._in_table and self._current_row:
                self.rows.append(self._current_row)
                self._current_row = []

    def handle_data(self, data):
        if self._in_table and self._in_cell:
            self._current_cell.append(data.strip())


def _request(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://q.10jqka.com.cn/thshy/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("gbk")


def _fetch_members_for_board(provider_code: str) -> list[dict]:
    """从同花顺网站抓取指定板块的成分股列表"""
    first_url = f"http://q.10jqka.com.cn/thshy/detail/code/{provider_code}/"
    first_html = _request(first_url, timeout=20)

    # Get page count
    page_count = 1
    m = re.search(r'class=[\"\']page_info[\"\'][^>]*>\s*(\d+)\s*/\s*(\d+)', first_html)
    if m:
        page_count = int(m.group(2))

    # Fetch all pages
    html_pages = [first_html]
    for page in range(2, page_count + 1):
        try:
            html_pages.append(_request(
                f"http://q.10jqka.com.cn/thshy/detail/code/{provider_code}/page/{page}/",
                timeout=15,
            ))
        except Exception as e:
            logger.warning(f"    第{page}页失败: {e}")
            break

    # Parse members
    seen = set()
    members = []
    for html in html_pages:
        parser = _THSMemberTableParser()
        parser.feed(html)
        headers = None
        for row in parser.rows:
            row_clean = [c.strip() for c in row if c.strip()]
            if any("代码" in c for c in row_clean) and any("名称" in c for c in row_clean):
                headers = row_clean
                continue
            if headers and len(row_clean) >= len(headers):
                row_dict = dict(zip(headers, row_clean, strict=False))
                code = re.search(r"\d{6}", row_dict.get("代码", ""))
                name = row_dict.get("名称", "").strip()
                if code and name:
                    sym = code.group(0)
                    exchange = "SSE" if sym.startswith(("5", "6", "9")) else ("BSE" if sym.startswith(("43", "83", "87", "88", "92")) else "SZSE")
                    key = (sym, exchange)
                    if key not in seen:
                        seen.add(key)
                        members.append({"symbol": sym, "exchange": exchange, "name": name})
    return members


def main():
    get_engine()
    db = SessionLocal()
    try:
        repo = StockBoardRepository(db)
        boards = repo.list_boards(category="行业板块")
        logger.info(f"数据库已有 {len(boards)} 个行业板块")

        ok = 0
        skipped = 0
        failed = []
        total_members = 0

        for i, board in enumerate(boards):
            name = board.name
            provider_code = getattr(board, "provider_code", None) or ""
            existing = repo.list_members(board=board)

            if existing:
                logger.info(f"  [{i+1}/{len(boards)}] ✅ {name}: 已有 {len(existing)} 只，跳过")
                total_members += len(existing)
                skipped += 1
                continue

            if not provider_code:
                logger.warning(f"  [{i+1}/{len(boards)}] ❌ {name}: 无 provider_code")
                failed.append(name)
                continue

            logger.info(f"  [{i+1}/{len(boards)}] {name} (code={provider_code})...")
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_fetch_members_for_board, provider_code)
                    members = future.result(timeout=40)
            except FutureTimeout:
                logger.warning(f"    ❌ 超时 (>40s)")
                failed.append(name)
                continue
            except Exception as e:
                logger.warning(f"    ❌ 失败: {e}")
                failed.append(name)
                continue

            if not members:
                logger.warning(f"    ❌ 空结果")
                failed.append(name)
                continue

            repo.replace_members(board=board, members=members, source="akshare")
            db.commit()
            logger.info(f"    ✅ {len(members)} 只")
            total_members += len(members)
            ok += 1

        # Phase 3: Update stock industries
        logger.info(f"\nPhase 3: 更新股票行业分类...")
        from apps.api.repositories.stocks import StockRepository
        from apps.api.models import Stock
        from sqlalchemy import select

        industry_by_symbol = {}
        for board in repo.list_boards(category="行业板块"):
            for member in repo.list_members(board=board):
                industry_by_symbol[(member.symbol, member.exchange, "A_SHARE")] = board.name

        stock_repo = StockRepository(db)
        updated = stock_repo.update_industries(industry_by_symbol)
        db.commit()

        logger.info(f"  更新 {updated} 只股票行业")
        logger.info(f"\n=== 完成 ===")
        logger.info(f"成功: {ok}, 跳过: {skipped}, 失败: {len(failed)}")
        logger.info(f"总成分股记录: {total_members}")
        if failed:
            logger.warning(f"失败的板块 ({len(failed)}): {failed}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
