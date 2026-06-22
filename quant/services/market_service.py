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
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


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


def get_news(keyword: str = "A股", limit: int = 20) -> List[Dict]:
    """获取新浪财经新闻（API直连）

    Args:
        keyword: 搜索关键词
        limit: 返回条数

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
        "page": "1",
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
    index_codes = ["sh000001", "sz399001", "sh000300", "sz399006"]
    return get_realtime_quotes(index_codes)


def get_sector_stocks(sector_code: str = "电力") -> List[Dict]:
    """获取板块内股票列表（通过搜索）

    注意：当前没有直接的板块行情API，通过关键词搜索获取相关股票

    Args:
        sector_code: 板块关键词

    Returns:
        对应板块的股票行情列表
    """
    # 常见板块股票硬编码映射
    SECTOR_MAP = {
        "电力": [
            "sh600900", "sh600025", "sh601985", "sh600021",
            "sh600027", "sh600116", "sh600795", "sh600023",
            "sh600726", "sz000591", "sz000883", "sz000875",
        ],
        "煤炭": [
            "sh601088", "sh601225", "sh600188", "sh601898",
            "sh601001", "sz000552", "sz002128",
        ],
        "银行": [
            "sh601398", "sh601288", "sh601939", "sh601328",
            "sh600036", "sh600016", "sh600000", "sz000001",
        ],
    }

    codes = SECTOR_MAP.get(sector_code, [])
    if not codes:
        return []

    return get_realtime_quotes(codes)


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
