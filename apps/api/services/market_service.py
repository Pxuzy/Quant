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

SECTOR_GROUPS = [
    # ── 行业板块 ──
    {"name": "银行", "category": "行业板块", "codes": ["sh601398", "sh601288", "sh601939", "sh601328", "sh600036", "sh600016", "sh600000", "sz000001"]},
    {"name": "电力", "category": "行业板块", "codes": ["sh600900", "sh600025", "sh601985", "sh600021", "sh600027", "sh600116", "sh600795", "sh600023", "sh600726", "sz000591", "sz000883", "sz000875"]},
    {"name": "煤炭", "category": "行业板块", "codes": ["sh601088", "sh601225", "sh600188", "sh601898", "sh601001", "sz000552", "sz002128"]},
    {"name": "白酒", "category": "行业板块", "codes": ["sh600519", "sz000858", "sz000568", "sh600809", "sh603369", "sz002304"]},
    {"name": "半导体", "category": "行业板块", "codes": ["sh688981", "sh688012", "sh688008", "sz300782", "sh603986", "sz002371"]},
    {"name": "医药生物", "category": "行业板块", "codes": ["sz000538", "sh600276", "sz300347", "sz002007", "sh600056", "sz002252", "sz300564", "sz002422"]},
    {"name": "新能源", "category": "行业板块", "codes": ["sh601012", "sz300274", "sz002459", "sh600438", "sh688599", "sz002129"]},
    {"name": "房地产", "category": "行业板块", "codes": ["sz000002", "sh600048", "sz002146", "sh601155", "sz000671", "sh600383"]},
    {"name": "汽车", "category": "行业板块", "codes": ["sz002594", "sh601633", "sh600104", "sz002460", "sz002812", "sh601236"]},
    {"name": "非银金融", "category": "行业板块", "codes": ["sh600030", "sh601688", "sh600837", "sz000776", "sh601211", "sz300059"]},
    {"name": "食品饮料", "category": "行业板块", "codes": ["sh600519", "sz000858", "sz000568", "sh600809", "sz002304", "sz399997"]},
    {"name": "交通运输", "category": "行业板块", "codes": ["sh601006", "sh600028", "sz002236", "sh601896", "sh600018", "sz000890"]},
    {"name": "电子", "category": "行业板块", "codes": ["sz002049", "sh688012", "sz002371", "sz300496", "sh603986", "sz000725"]},
    {"name": "家用电器", "category": "行业板块", "codes": ["sz000651", "sh600690", "sz002032", "sz000333", "sh603868", "sz002508"]},
    {"name": "机械设备", "category": "行业板块", "codes": ["sz000333", "sh601012", "sz300033", "sh600588", "sz002097", "sh688017"]},
    {"name": "基础化工", "category": "行业板块", "codes": ["sh600309", "sz002497", "sh603027", "sz002254", "sh600426", "sz300220"]},
    {"name": "有色金属", "category": "行业板块", "codes": ["sh601899", "sh600362", "sz002460", "sh601168", "sz000878", "sh601212"]},
    {"name": "建筑装饰", "category": "行业板块", "codes": ["sh601668", "sz002304", "sh600856", "sz002081", "sh601398", "sz300970"]},
    # ── 概念板块 ──
    {"name": "人工智能", "category": "概念板块", "codes": ["sz300033", "sh600570", "sz300418", "sh688256", "sz002230", "sh603019"]},
    {"name": "新能源车", "category": "概念板块", "codes": ["sz300750", "sz002594", "sh601633", "sh600104", "sz002460", "sz002812"]},
    {"name": "光伏", "category": "概念板块", "codes": ["sh601012", "sz300274", "sz002459", "sh600438", "sh688599", "sz002129"]},
    {"name": "芯片", "category": "概念板块", "codes": ["sh688981", "sh688012", "sh688008", "sz300782", "sh603986", "sz002371"]},
    {"name": "5G", "category": "概念板块", "codes": ["sz002093", "sh600522", "sz300308", "sz002281", "sh688012", "sz300418"]},
    {"name": "创新药", "category": "概念板块", "codes": ["sh688513", "sz300347", "sh600276", "sz002007", "sh688169", "sz300564"]},
    {"name": "军工", "category": "概念板块", "codes": ["sh601989", "sz002414", "sh688012", "sz300520", "sh600893", "sz000768"]},
    {"name": "白酒", "category": "概念板块", "codes": ["sh600519", "sz000858", "sz000568", "sh600809", "sh603369", "sz002304"]},
    {"name": "碳中和", "category": "概念板块", "codes": ["sh601012", "sz300274", "sz002459", "sh600438", "sz002129", "sh601985"]},
    {"name": "华为产业链", "category": "概念板块", "codes": ["sz002241", "sh688012", "sz300496", "sz002049", "sh603986", "sz300782"]},
    {"name": "数字货币", "category": "概念板块", "codes": ["sz300033", "sh600570", "sz002230", "sh688256", "sz300418", "sz000712"]},
    {"name": "医美", "category": "概念板块", "codes": ["sz000858", "sz002304", "sh600809", "sz300347", "sz002007", "sz002422"]},
    # ── 指数板块 ──
    {"name": "上证指数", "category": "指数板块", "codes": ["sh000001"]},
    {"name": "深证成指", "category": "指数板块", "codes": ["sz399001"]},
    {"name": "沪深300", "category": "指数板块", "codes": ["sh000300"]},
    {"name": "创业板指", "category": "指数板块", "codes": ["sz399006"]},
    {"name": "科创50", "category": "指数板块", "codes": ["sh000688"]},
    {"name": "中证500", "category": "指数板块", "codes": ["sh000905"]},
    {"name": "中证1000", "category": "指数板块", "codes": ["sh000852"]},
]

SECTOR_CATEGORY_ORDER = ["行业板块", "概念板块", "指数板块"]
SECTOR_CODE_MAP = {group["name"]: group["codes"] for group in SECTOR_GROUPS}

# ── 股票 → 板块 映射（每只股票可属于多个板块）──
STOCK_SECTOR_MAP: Dict[str, List[str]] = {}
for _g in SECTOR_GROUPS:
    for _c in _g["codes"]:
        STOCK_SECTOR_MAP.setdefault(_c, []).append(_g["name"])


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


def get_stock_sectors(code: str) -> List[str]:
    """获取股票所属的板块名称列表

    Args:
        code: 股票代码，如 'sh600900'

    Returns:
        所属板块名称列表，如 ['电力', '碳中和']
    """
    return STOCK_SECTOR_MAP.get(code, [])


def get_sector_constituents(sector_name: str) -> List[Dict]:
    """获取板块成分股实时行情

    Args:
        sector_name: 板块名称，如 '银行'、'人工智能'

    Returns:
        成分股实时行情列表，包含股票所属板块信息
    """
    codes = SECTOR_CODE_MAP.get(sector_name, [])
    if not codes:
        return []

    quotes = get_realtime_quotes(codes)
    # 为每只股票附加所属板块标签
    for q in quotes:
        q["sectors"] = get_stock_sectors(q["code"])
    return quotes


def get_sector_stocks(sector_code: str = "电力") -> List[Dict]:
    """获取板块内股票列表（通过搜索）

    注意：当前没有直接的板块行情API，通过关键词搜索获取相关股票

    Args:
        sector_code: 板块关键词

    Returns:
        对应板块的股票行情列表，包含所属板块标签
    """
    codes = SECTOR_CODE_MAP.get(sector_code, [])
    if not codes:
        return []

    quotes = get_realtime_quotes(codes)
    for q in quotes:
        q["sectors"] = get_stock_sectors(q["code"])
    return quotes


def get_sector_rankings(categories: Optional[List[str]] = None) -> List[Dict]:
    """获取板块级排行。

    当前腾讯板块行情不可用，先用代表成份股或指数行情聚合出板块涨跌、涨跌家数和领涨标的。
    """
    requested_categories = [
        category for category in (categories or SECTOR_CATEGORY_ORDER)
        if category in SECTOR_CATEGORY_ORDER
    ]
    if not requested_categories:
        requested_categories = SECTOR_CATEGORY_ORDER

    groups = [
        group for category in requested_categories
        for group in SECTOR_GROUPS
        if group["category"] == category
    ]

    all_codes = sorted({code for group in groups for code in group["codes"]})
    quotes = []
    for start in range(0, len(all_codes), 30):
        quotes.extend(get_realtime_quotes(all_codes[start:start + 30]))

    quotes_by_code = {quote["code"]: quote for quote in quotes}

    rows = []
    for group in groups:
        quotes = [quotes_by_code[code] for code in group["codes"] if code in quotes_by_code]
        leader = max(quotes, key=lambda item: item.get("change_pct", 0), default=None)
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

    grouped_rows = []
    for category in requested_categories:
        category_rows = [row for row in rows if row["category"] == category]
        grouped_rows.extend(sorted(category_rows, key=lambda item: item["change_pct"], reverse=True))

    return grouped_rows


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
