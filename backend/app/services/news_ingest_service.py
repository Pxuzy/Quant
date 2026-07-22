"""新闻抓取管线 — 定时拉取 + 存储 + 去重 + 多源"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode


from backend.app.db.session import SessionLocal, get_engine
from backend.app.models.entities import NewsArticle  # noqa: F401 register model

# Ensure engine is initialized at module level
get_engine()
from backend.app.repositories.news_articles import NewsRepository
from backend.app.services._http import _request

logger = logging.getLogger(__name__)

# ── 抓取配置 ──
DEFAULT_KEYWORDS = ["A股", "股市", "财经", "央行", "新能源", "半导体"]
MAX_PER_KEYWORD = 20
NEWS_SOURCES = ["sina", "cls"]

_NEWS_CATEGORY_KEYWORDS = {
    "政策": ["央行", "降准", "降息", "政策", "监管", "国务院", "证监会", "财政", "货币", "利率"],
    "公司": ["分红", "业绩", "公告", "减持", "增持", "回购", "营收", "净利润", "合同", "中标", "募资"],
    "行业": ["板块", "行业", "光伏", "新能源", "芯片", "人工智能", "汽车", "医药", "消费", "半导体", "锂电"],
}


def _classify_news(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    for category, keywords in _NEWS_CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "市场"


def get_news(keyword: str = "A股", limit: int = 20, page: int = 1) -> list[dict]:
    """获取新浪财经新闻。"""
    params = urlencode({
        "pageid": "153", "lid": "2516", "k": keyword,
        "num": str(min(limit, 50)), "page": str(page),
    })
    url = f"https://feed.mix.sina.com.cn/api/roll/get?{params}"
    try:
        data = json.loads(_request(url))
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

# ── 辅助函数 ──

def _dedup_key(title: str, url: str) -> str:
    """生成去重 key（URL 优先，title hash 兜底）"""
    return url or hashlib.md5(title.encode()).hexdigest()[:16]


def fetch_news_from_sina(keyword: str, limit: int = 20) -> list[dict]:
    """从新浪财经拉取新闻"""
    params = urlencode({
        "pageid": "153", "lid": "2516", "k": keyword,
        "num": str(min(limit, 50)), "page": "1",
    })
    url = f"https://feed.mix.sina.com.cn/api/roll/get?{params}"

    try:
        data = json.loads(_request(url))
    except Exception as e:
        logger.error(f"新浪请求失败 [{keyword}]: {e}")
        return []

    results = []
    for item in data.get("result", {}).get("data", [])[:limit]:
        title = item.get("title", "").strip()
        if not title:
            continue
        created_ts = int(item.get("ctime", 0))
        results.append({
            "title": title,
            "url": item.get("url", ""),
            "summary": item.get("summary", "")[:200].strip(),
            "source": "sina",
            "category": _classify_news(title, item.get("summary", "")),
            "external_id": str(item.get("oid", "")) or _dedup_key(title, item.get("url", "")),
            "published_at": (
                datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else None
            ),
        })
    return results


def fetch_news_from_cls(keyword: str = "", limit: int = 20) -> list[dict]:
    """从财联社拉取新闻（telegraph API，实时快讯流）"""
    params = urlencode({
        "app": "CailianpressWeb", "os": "web", "sv": "8.7.9",
    })
    url = f"https://www.cls.cn/api/cache?{params}&name=telegraph"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Referer": "https://www.cls.cn/telegraph"}
    try:
        data = json.loads(_request(url, headers=headers, timeout=15))
    except Exception as e:
        logger.error(f"财联社请求失败 [{keyword}]: {e}")
        return []

    items = data.get("data", {}).get("roll_data", [])
    results = []
    for item in items[:limit]:
        title = (item.get("title", "") or "").strip()
        brief = (item.get("brief", "") or "").strip()
        if not title:
            title = brief[:80] if brief else ""
        if not title:
            continue
        ctime = item.get("ctime", 0)
        if isinstance(ctime, (int, float)) and ctime > 1e12:
            ctime = ctime / 1000
        results.append({
            "title": title,
            "url": f"https://www.cls.cn/telegraph/{item.get('id', '')}",
            "summary": brief[:200].strip(),
            "source": "cls",
            "category": _classify_news(title, brief),
            "external_id": str(item.get("id", "")) or _dedup_key(title, ""),
            "published_at": (
                datetime.fromtimestamp(ctime, tz=timezone.utc) if ctime else None
            ),
        })
    return results


def extract_related_symbols(title: str, summary: str) -> list[str]:
    """从新闻标题/摘要中提取相关股票代码"""
    import re
    text = title + " " + (summary or "")
    # 匹配 6位数字 股票代码
    codes = re.findall(r"\b(\d{6})\b", text)
    # 过滤掉明显不是股票的数字
    valid_codes = [c for c in codes if c.startswith("0") or c.startswith("3") or c.startswith("6")]
    return list(set(valid_codes))[:5]


def run_news_ingest(*, keywords: list[str] | None = None, limit_per: int = MAX_PER_KEYWORD,
                    sources: list[str] | None = None) -> dict:
    """
    执行新闻抓取管线（多源）

    Args:
        keywords: 搜索关键词列表
        limit_per: 每个关键词每个源的抓取数
        sources: 数据源列表，默认 ["sina",    Returns:
        {"fetched": N, "new": M, "total": T}
    """
    if keywords is None:
        keywords = DEFAULT_KEYWORDS
    if sources is None:
        sources = NEWS_SOURCES

    db = SessionLocal()
    try:
        repo = NewsRepository(db)
        all_fetched = 0
        total_new = 0
        source_stats: dict[str, dict] = {}

        for source in sources:
            fetcher = _FETCHERS.get(source)
            if not fetcher:
                logger.warning(f"未知数据源: {source}, 跳过")
                continue

            src_fetched = src_new = 0
            for keyword in keywords:
                articles = fetcher(keyword, limit=limit_per)
                src_fetched += len(articles)
                for article in articles:
                    article["related_symbols"] = extract_related_symbols(
                        article["title"], article.get("summary", "")
                    )
                src_new += repo.upsert_many(articles)
                logger.info(f"  [{source}/{keyword}] 获取 {len(articles)} 条, 新增 {src_new} 条")

            source_stats[source] = {"fetched": src_fetched, "new": src_new}
            all_fetched += src_fetched
            total_new += src_new

        db.commit()
        total_in_db = repo.count()
        logger.info(f"� 完成: 抓取 {all_fetched}, 新增 {total_new}, 总计 {total_in_db}")

        return {
            "fetched": all_fetched,
            "new": total_new,
            "total": total_in_db,
            "keywords": keywords,
            "sources": source_stats,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ 新闻管线失败: {e}")
        raise
    finally:
        db.close()


def cleanup_old_news(keep_days: int = 30) -> int:
    """清理过期新闻"""
    db = SessionLocal()
    try:
        repo = NewsRepository(db)
        deleted = repo.delete_old(keep_days=keep_days)
        db.commit()
        logger.info(f"🧹 清理 {deleted} 条过期新闻 (>{keep_days}天)")
        return deleted
    except Exception as e:
        db.rollback()
        logger.error(f"清理失败: {e}")
        return 0
    finally:
        db.close()


# ── 数据源注册表 ──

_FETCHERS: dict[str, callable] = {
    "sina": fetch_news_from_sina,
    "cls": fetch_news_from_cls,
}


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run_news_ingest()
    print(json.dumps(result, ensure_ascii=False, indent=2))
