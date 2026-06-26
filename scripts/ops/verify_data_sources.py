"""数据源验证脚本

运行: python scripts/verify_data_sources.py

验证3个API的连通性和返回数据格式：
  1. 腾讯历史K线 (web.ifzq.gtimg.cn)
  2. 雪球热门新闻 (xueqiu.com)
  3. 腾讯板块行情 (qt.gtimg.cn)

不走系统代理，直连上述域名，超时10秒。
"""

from __future__ import annotations

import json
import logging
import socket
import sys
import urllib.error
import urllib.request

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 超时（秒）
TIMEOUT = 10

# 不走代理的域名（直连）
NO_PROXY_HOSTS = [
    "web.ifzq.gtimg.cn",
    "qt.gtimg.cn",
    "xueqiu.com",
]


def _build_no_proxy_opener() -> urllib.request.OpenerDirector:
    """构建不走系统代理的 opener（直连腾讯/雪球）。"""
    proxy_handler = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(proxy_handler)


def _fetch_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = TIMEOUT,
) -> dict | list | None:
    """
    发送 GET 请求，返回解析后的 JSON。

    失败时返回 None，异常由调用方决定是否打印。
    """
    req = urllib.request.Request(url, headers=headers or {})
    opener = _build_no_proxy_opener()
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("请求失败: %s — %s", url, exc)
        return None


# =============================================================================
# API 1：腾讯历史K线
# =============================================================================


def verify_tencent_kline() -> bool:
    """
    验证：https://web.ifzq.gtimg.cn/appstock/app/fqkline/get

    期望返回 JSON，结构类似：
      {"data": {"sh600900": {"qfqday": [[日期, 开, 收, 高, 低, 量], ...]}}}
    """
    symbol = "sh600900"  # 长江电力
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={symbol},day,,,,,{5},qfq"
    )
    logger.info("[API-1] 腾讯历史K线: %s", url)

    data = _fetch_json(url)
    if data is None:
        logger.warning("[API-1] ❌ 获取数据失败")
        return False

    # 尝试提取 qfqday 数据
    try:
        stock_data = data.get("data", {}).get(symbol, {})
        qfqday = stock_data.get("qfqday") or stock_data.get("day") or []
        if not qfqday:
            raise ValueError("qfqday/day 字段为空或不存在")
    except Exception as exc:
        logger.warning("[API-1] ❌ 数据格式不符: %s", exc)
        logger.debug("实际返回: %s", json.dumps(data, ensure_ascii=False)[:300])
        return False

    logger.info("[API-1] ✅ 获取成功，共 %d 条", len(qfqday))
    for row in qfqday[:3]:
        logger.info("    样本: %s", row)
    return True


# =============================================================================
# API 2：雪球热门新闻
# =============================================================================


def verify_xueqiu_news() -> bool:
    """
    验证：https://xueqiu.com/query.json

    需加 User-Agent header，否则返回 403。
    期望返回 JSON，结构类似：
      {"list": [{"title": "...", "url": "...", "created_at": ..., ...}]}
    """
    url = "https://xueqiu.com/query.json?q=A%E8%82%A1&type=post&count=5&page=1"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://xueqiu.com",
    }
    logger.info("[API-2] 雪球热门新闻: %s", url)

    data = _fetch_json(url, headers=headers)
    if data is None:
        logger.warning("[API-2] ❌ 获取数据失败（可能需要 cookie）")
        return False

    # 尝试提取 list 数据
    try:
        items = data.get("list") or data.get("items") or []
        if not isinstance(items, list):
            raise ValueError(f"list 字段类型错误: {type(items)}")
    except Exception as exc:
        logger.warning("[API-2] ❌ 数据格式不符: %s", exc)
        logger.debug("实际返回: %s", json.dumps(data, ensure_ascii=False)[:300])
        return False

    logger.info("[API-2] ✅ 获取成功，共 %d 条", len(items))
    for item in items[:3]:
        title = item.get("title") or item.get("text") or str(item)[:60]
        logger.info("    样本: %s", title)
    return True


# =============================================================================
# API 3：腾讯板块行情
# =============================================================================


def verify_tencent_sector() -> bool:
    """
    验证：https://qt.gtimg.cn/q=s_bk0481（电力板块）

    期望返回文本格式，以 ~ 分隔字段：
      v_b_s_bk0481="1~电力指数~...~涨跌幅~..."
    """
    url = "https://qt.gtimg.cn/q=s_bk0481"
    logger.info("[API-3] 腾讯板块行情: %s", url)

    req = urllib.request.Request(url)
    opener = _build_no_proxy_opener()
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
    except Exception as exc:
        logger.error("[API-3] ❌ 请求失败: %s", exc)
        return False

    # 解析文本格式
    lines = [ln for ln in raw.split("\n") if ln.strip()]
    if not lines:
        logger.warning("[API-3] ❌ 返回为空")
        return False

    # 第一行通常是 v_b_s_bk0481="..."
    first_line = lines[0]
    # 格式: v_b_s_bk0481="1~板块名~..."
    if '"' in first_line:
        try:
            parts = first_line.split('"')[1].split("~")
        except (IndexError, ValueError):
            parts = []
    else:
        parts = first_line.split("~")

    logger.info("[API-3] ✅ 获取成功，解析字段数: %d", len(parts))
    logger.info("    前10字段: %s", parts[:10])
    return len(parts) >= 5


# =============================================================================
# 主函数
# =============================================================================


def main() -> None:
    logger.info("=" * 60)
    logger.info("数据源验证开始（超时=%d秒，不走系统代理）", TIMEOUT)
    logger.info("=" * 60)

    results: dict[str, bool] = {}

    logger.info("")
    results["腾讯历史K线"] = verify_tencent_kline()

    logger.info("")
    results["雪球新闻"] = verify_xueqiu_news()

    logger.info("")
    results["腾讯板块行情"] = verify_tencent_sector()

    logger.info("")
    logger.info("=" * 60)
    logger.info("验证结果汇总:")
    for name, ok in results.items():
        logger.info("  %s: %s", "✅" if ok else "❌", name)
    logger.info("=" * 60)

    available = sum(results.values())
    sys.exit(0 if available == len(results) else 1)


if __name__ == "__main__":
    main()