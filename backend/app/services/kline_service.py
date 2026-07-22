"""K线服务 - 历史K线、图表数据"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from backend.app.repositories.daily_bars import DailyBarRepository
from backend.app.services._http import _request

logger = logging.getLogger(__name__)

# ── K线解析 ──

_KLINE_KEY_MAP = {"day": "qfqday", "week": "qfqweek", "month": "qfqmonth"}
_TENCENT_KLINE_PAGE_SIZE = 800


def _parse_kline_response(text: str, code: str, period: str, count: int) -> List[Dict]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    data_items = data.get("data", {}) if isinstance(data, dict) else {}
    if not isinstance(data_items, dict):
        return []
    period_key = _KLINE_KEY_MAP.get(period, "qfqday")
    results = []
    safe_count = max(1, count)
    for stock_data in data_items.values():
        if not isinstance(stock_data, dict):
            continue
        klines = stock_data.get(period_key, [])
        if not isinstance(klines, list):
            continue
        for k in klines[-safe_count:]:
            try:
                results.append(
                    {
                        "date": k[0],
                        "open": float(k[1]),
                        "high": float(k[3]),
                        "close": float(k[2]),
                        "low": float(k[4]),
                        "volume": int(float(k[5])) if len(k) > 5 else 0,
                    }
                )
            except (ValueError, IndexError):
                continue
    return results


def _kline_start_date(end_at: datetime, period: str, count: int) -> str:
    if period == "day":
        return (end_at - timedelta(days=count * 2)).strftime("%Y-%m-%d")
    if period == "week":
        return (end_at - timedelta(weeks=count * 2)).strftime("%Y-%m-%d")
    return (end_at - timedelta(days=count * 60)).strftime("%Y-%m-%d")


def _strip_stock_prefix(code: str) -> str:
    value = code.strip().lower()
    if value.startswith(("sh", "sz", "bj")):
        return value[2:]
    return value


def _daily_bar_to_kline(row: dict) -> Dict:
    trade_date = row["trade_date"]
    return {
        "date": trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date),
        "open": round(float(row["open"]), 6),
        "high": round(float(row["high"]), 6),
        "close": round(float(row["close"]), 6),
        "low": round(float(row["low"]), 6),
        "volume": int(float(row.get("volume") or 0)),
    }


def _get_governed_daily_kline(code: str, count: int) -> List[Dict]:
    symbol = _strip_stock_prefix(code)
    if not symbol:
        return []

    rows = [
        row
        for row in DailyBarRepository().symbol_daily_bars(symbol=symbol, market="A_SHARE")
        if (row.get("adjust_type") or "none") == "none"
    ]
    if not rows:
        return []

    return [_daily_bar_to_kline(row) for row in rows[-max(1, count) :]]


def get_history_kline(code: str, period: str = "day", count: int = 100, adjust: str = "qfq") -> List[Dict]:
    """获取历史K线（腾讯API直连）"""
    if period == "day":
        governed_rows = _get_governed_daily_kline(code, count)
        if governed_rows:
            return governed_rows

    remaining = max(1, count)
    end_at = datetime.now()
    by_date: dict[str, Dict] = {}

    while remaining > 0:
        page_count = min(remaining, _TENCENT_KLINE_PAGE_SIZE)
        end_date = end_at.strftime("%Y-%m-%d")
        start_date = _kline_start_date(end_at, period, page_count)
        param = f"{code},{period},{start_date},{end_date},{page_count},{adjust}"
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={param}"
        try:
            text = _request(url, encoding="gbk")
        except Exception as e:
            logger.error(f"K线请求失败: {e}")
            break

        rows = _parse_kline_response(text, code, period, page_count)
        if not rows:
            break
        for row in rows:
            by_date[row["date"]] = row

        remaining -= page_count
        try:
            end_at = datetime.strptime(rows[0]["date"], "%Y-%m-%d") - timedelta(days=1)
        except ValueError:
            break

    return sorted(by_date.values(), key=lambda item: item["date"])[-max(1, count) :]
