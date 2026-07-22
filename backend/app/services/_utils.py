"""行情服务共享的文本、代码与数据转换工具。"""

from __future__ import annotations

import re
from typing import Dict


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
