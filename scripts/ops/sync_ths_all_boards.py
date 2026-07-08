"""
全量同步同花顺 90 个行业板块的成分股和股票行业分类。
优点：逐个板块独立超时，不卡死整个流程。
"""
import sys
import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

os.environ.setdefault("TQDM_DISABLE", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.db.session import SessionLocal, get_engine
from backend.app.repositories.stock_boards import StockBoardRepository
from backend.app.services.market_service import (
    _fetch_ths_industry_boards,
    _fetch_board_members,
    _sync_stock_industries_from_board_members,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_ths")


def sync_one_board(repo, board, timeout=30):
    """同步单个板块的成分股"""
    name = board.name
    try:
        members = _fetch_board_members("行业板块", name)
    except Exception as e:
        return {"name": name, "status": "error", "error": str(e), "members": 0}
    if not members:
        return {"name": name, "status": "empty", "error": "no members", "members": 0}
    written = repo.replace_members(board=board, members=members, source="akshare")
    return {"name": name, "status": "ok", "error": None, "members": written}


def main():
    get_engine()

    # Phase 1: sync board list
    logger.info("Phase 1: 同步板块列表")
    records = _fetch_ths_industry_boards()
    logger.info(f"  获取到 {len(records)} 个板块")

    db = SessionLocal()
    try:
        repo = StockBoardRepository(db)
        boards_written = repo.upsert_boards(records)
        db.commit()
        logger.info(f"  写入 {boards_written} 个板块到数据库")

        # Phase 2: sync members for each board
        boards = repo.list_boards(category="行业板块")
        logger.info(f"Phase 2: 同步 {len(boards)} 个板块成分股")

        results = {"ok": 0, "error": 0, "empty": 0, "total_members": 0, "failed": []}

        for i, board in enumerate(boards):
            board_name = board.name
            logger.info(f"  [{i+1}/{len(boards)}] {board_name}...")

            # Check if already has members
            existing = repo.list_members(board=board)
            if existing:
                logger.info(f"    已有 {len(existing)} 条成分股，跳过")
                results["ok"] += 1
                results["total_members"] += len(existing)
                continue

            # Use ThreadPoolExecutor for timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(sync_one_board, repo, board)
                try:
                    r = future.result(timeout=35)
                except TimeoutError:
                    logger.warning(f"    ❌ 超时 (>35s)")
                    results["error"] += 1
                    results["failed"].append({"name": board_name, "error": "timeout"})
                    continue
                except Exception as e:
                    logger.warning(f"    ❌ 异常: {e}")
                    results["error"] += 1
                    results["failed"].append({"name": board_name, "error": str(e)})
                    continue

            if r["status"] == "ok":
                logger.info(f"    ✅ {r['members']} 只")
                results["ok"] += 1
                results["total_members"] += r["members"]
            else:
                logger.warning(f"    ❌ {r.get('error', 'unknown')}")
                results["error"] += 1
                results["failed"].append(r)

            db.commit()

        # Phase 3: update stock industries from board members
        logger.info("Phase 3: 更新股票行业分类")
        updated = _sync_stock_industries_from_board_members(db, repo)
        db.commit()
        logger.info(f"  更新 {updated} 只股票行业")

        logger.info(f"\n=== 完成 ===")
        logger.info(f"成功: {results['ok']}, 失败: {results['error']}")
        logger.info(f"总成分股记录: {results['total_members']}")
        logger.info(f"更新股票: {updated}")
        if results["failed"]:
            logger.warning(f"失败的板块: {[f['name'] for f in results['failed']]}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
