"""新闻抓取入口脚本 — 由 cron job 调用"""
import logging
import sys

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("news-ingest")

from backend.app.services.news_ingest_service import run_news_ingest

if __name__ == "__main__":
    log.info("Starting news ingest...")
    result = run_news_ingest()
    log.info(f"Done: fetched={result['fetched']}, new={result['new']}, total={result['total']}")
