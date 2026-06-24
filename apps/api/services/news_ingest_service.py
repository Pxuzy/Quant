"""新闻抓取管线 — 定时拉取 + 存储 + 去重"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.api.db.session import SessionLocal, get_engine, init_db
from apps.api.models.entities import NewsArticle  # noqa: F401 register model

# Ensure engine is initialized at module level
get_engine()
from apps.api.repositories.news_articles import NewsRepository
from apps.api.services.market_service import _classify_news, _request

logger = logging.getLogger(__name__)

# ── 抓取配置 ──
DEFAULT_KEYWORDS = ["A股", "股市", "财经", "央行", "新能源", "半导体"]
MAX_PER_KEYWORD = 20
NEWS_SOURCE = "sina"


def fetch_news_from_sina(keyword: str, limit: int = 20) -> list[dict]:
    """从新浪财经拉取新闻"""
    import urllib.parse
    import json

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
        logger.error(f"新闻请求失败 [{keyword}]: {e}")
        return []

    items = data.get("result", {}).get("data", [])
    results = []

    for item in items[:limit]:
        try:
            created_ts = int(item.get("ctime", 0))
            published_at = (
                datetime.fromtimestamp(created_ts, tz=timezone.utc)
                if created_ts
                else None
            )

            title = item.get("title", "").strip()
            summary = item.get("summary", "")[:200].strip()
            if not title:
                continue

            results.append({
                "title": title,
                "url": item.get("url", ""),
                "summary": summary,
                "source": NEWS_SOURCE,
                "category": _classify_news(title, summary),
                "external_id": str(item.get("oid", "")) or title,  # 优先 oid，fallback title
                "published_at": published_at,
            })
        except Exception as e:
            logger.warning(f"解析新闻失败: {e}")
            continue

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


def run_news_ingest(*, keywords: list[str] | None = None, limit_per: int = MAX_PER_KEYWORD) -> dict:
    """
    执行新闻抓取管线
    
    Returns:
        {"fetched": N, "new": M, "total": T}
    """
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    db = SessionLocal()
    try:
        repo = NewsRepository(db)
        all_fetched = 0
        total_new = 0

        for keyword in keywords:
            logger.info(f"📰 抓取新闻 [{keyword}]...")
            articles = fetch_news_from_sina(keyword, limit=limit_per)
            all_fetched += len(articles)

            # Enrich with related symbols
            for article in articles:
                article["related_symbols"] = extract_related_symbols(
                    article["title"], article.get("summary", "")
                )

            # Upsert
            new_count = repo.upsert_many(articles)
            total_new += new_count
            logger.info(f"  ✅ [{keyword}] 获取 {len(articles)} 条, 新增 {new_count} 条")

        db.commit()

        total_in_db = repo.count()
        logger.info(f"📊 新闻管线完成: 抓取 {all_fetched}, 新增 {total_new}, 总计 {total_in_db}")

        return {
            "fetched": all_fetched,
            "new": total_new,
            "total": total_in_db,
            "keywords": keywords,
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


if __name__ == "__main__":
    import sys, json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = run_news_ingest()
    print(json.dumps(result, ensure_ascii=False, indent=2))
