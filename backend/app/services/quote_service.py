"""实时行情服务 - 行情查询、股票搜索。"""

from __future__ import annotations

import contextlib
import io
import logging
import re
import urllib.parse
from importlib import import_module
from typing import Dict, List

from backend.app.services._http import _request

logger = logging.getLogger(__name__)


def _import_akshare():
    import os

    os.environ.setdefault("TQDM_DISABLE", "1")
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        return import_module("akshare")


_QUOTE_FIELD_MAP = {
    1: "name",
    3: "price",
    31: "change",
    32: "change_pct",
    5: "open",
    33: "high",
    34: "low",
    6: "volume",
    37: "amount",
    39: "pe",
    46: "pb",
    38: "turnover",
    9: "bid1_price",
    10: "bid1_vol",
    19: "ask1_price",
    20: "ask1_vol",
    4: "prev_close",
}


def _parse_tencent_quote(line: str) -> dict | None:
    code_match = re.search(r"v_([a-z]{2}\d{6})", line)
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
