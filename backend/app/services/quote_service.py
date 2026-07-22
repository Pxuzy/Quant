"""实时行情服务 - 行情查询、股票搜索、新闻"""

import contextlib
import io
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from importlib import import_module
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── 工具函数（共享） ──

_request_cache: dict[str, tuple[float, str]] = {}


def _request(url: str, headers: dict = None, timeout: int = 10, encoding: str = "utf-8") -> str:
    now = time.time()
    cached = _request_cache.get(url)
    if cached and (now - cached[0]) < 2.0:
        return cached[1]
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = resp.read().decode(encoding, errors="ignore")
    _request_cache[url] = (now, result)
    return result


def _clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").replace("\xa0", " ").strip()
    return "" if text.lower() in {"", "none", "nan", "nat", "--", "-"} else text


def _to_float(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if value != value else float(value)
    text = _clean_text(value).replace(",", "").replace("%", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _to_int(value) -> int:
    n = _to_float(value)
    return int(n) if n is not None else 0


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
        "code": code, "name": name, "price": 0, "change": 0, "change_pct": 0,
        "open": 0, "high": 0, "low": 0, "volume": 0, "amount": 0,
        "pe": 0, "pb": 0, "turnover": 0, "bid1_price": 0, "bid1_vol": 0,
        "ask1_price": 0, "ask1_vol": 0, "prev_close": 0, "sectors": sectors or [],
    }


def _member_from_row(row: dict) -> dict | None:
    raw_symbol = _clean_text(row.get("代码") or row.get("code"))
    stock_name = _clean_text(row.get("名称") or row.get("name"))
    m = re.search(r"\d{1,6}", raw_symbol)
    if not m or not stock_name:
        return None
    symbol = m.group(0).zfill(6)
    return {"symbol": symbol, "exchange": _exchange_from_symbol(symbol), "name": stock_name}


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


def _import_akshare():
    import os
    os.environ.setdefault("TQDM_DISABLE", "1")
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        return import_module("akshare")


# ── 实时行情解析 ──

_QUOTE_FIELD_MAP = {
    1: "name", 3: "price", 31: "change", 32: "change_pct",
    5: "open", 33: "high", 34: "low", 6: "volume", 37: "amount",
    39: "pe", 46: "pb", 38: "turnover", 9: "bid1_price", 10: "bid1_vol",
    19: "ask1_price", 20: "ask1_vol", 4: "prev_close",
}


def _parse_tencent_quote(line: str) -> dict | None:
    code_match = re.search(r'v_([a-z]{2}\d{6})', line)
    if not code_match:
        return None
    code = code_match.group(1)
    raw_val = line.split("=", 1)[1].strip('"')
    fields = raw_val.split("~")
    if len(fields) < 48:
        return None
    try:
        result = {"code": code}
        for idx, key in _QUOTE_FIELD_MAP.items():
            val = fields[idx]
            if key == "name":
                result[key] = val
            elif key in ("volume", "bid1_vol", "ask1_vol"):
                result[key] = int(float(val)) if val else 0
            else:
                result[key] = float(val) if val else 0
        return result
    except (ValueError, IndexError):
        return None


def get_realtime_quotes(codes: List[str]) -> List[Dict]:
    """获取实时行情（腾讯API直连）"""
    if not codes:
        return []
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
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
        quote = _parse_tencent_quote(line)
        if quote:
            results.append(quote)
    return results


def search_stock(keyword: str, limit: int = 10) -> List[Dict]:
    """搜索股票（腾讯API直连）"""
    params = urllib.parse.urlencode({"q": keyword, "t": "gp"})
    url = f"https://smartbox.gtimg.cn/s3/?v=2&q={params}&t=gp"
    try:
        text = _request(url, encoding="gbk")
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return []
    match = re.search(r'v_hint="([^"]*)"', text)
    if not match:
        return []
    results = []
    for item in match.group(1).split("^"):
        parts = item.split("~")
        if len(parts) >= 4:
            results.append({"code": f"{parts[0]}{parts[1]}", "name": parts[3], "market": parts[0]})
    return results[:limit]


def get_index_quotes() -> List[Dict]:
    """获取大盘指数实时行情"""
    return get_realtime_quotes(["sh000001", "sz399001", "sh000300", "sz399006", "sh000688", "sh000905", "sh000852"])


# ── 新闻 ──

_NEWS_CATEGORY_KEYWORDS = {
    "政策": ["央行", "降准", "降息", "政策", "监管", "国务院", "证监会", "财政", "货币", "利率"],
    "公司": ["分红", "业绩", "公告", "减持", "增持", "回购", "营收", "净利润", "合同", "中标", "募资"],
    "行业": ["板块", "行业", "光伏", "新能源", "芯片", "人工智能", "汽车", "医药", "消费", "半导体", "锂电"],
}


def _classify_news(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    for category, keywords in _NEWS_CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return category
    return "市场"


def get_news(keyword: str = "A股", limit: int = 20, page: int = 1) -> List[Dict]:
    """获取新浪财经新闻"""
    params = urllib.parse.urlencode({
        "pageid": "153", "lid": "2516", "k": keyword,
        "num": str(min(limit, 50)), "page": str(page),
    })
    url = f"https://feed.mix.sina.com.cn/api/roll/get?{params}"
    try:
        text = _request(url)
        data = json.loads(text)
    except Exception as e:
        logger.error(f"新闻请求失败: {e}")
        return []
    results = []
    for item in data.get("result", {}).get("data", [])[:limit]:
        try:
            created_ts = int(item.get("ctime", 0))
            results.append({
                "title": item.get("title", ""), "url": item.get("url", ""),
                "summary": item.get("summary", "")[:200],
                "source": item.get("media_name", "新浪"),
                "created_at": (
                    datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
                    if created_ts else ""
                ),
                "category": _classify_news(item.get("title", ""), item.get("summary", "")),
            })
        except Exception as e:
            logger.warning(f"解析新闻失败: {e}")
    return results
