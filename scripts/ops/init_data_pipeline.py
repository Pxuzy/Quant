#!/usr/bin/env python3
"""
Quant 数据管线初始化脚本
- 全量股票列表同步 → SQLite
- 示例股票3年日K线 → Parquet/DuckDB
- 交易日历同步 → SQLite
"""

import sys
import os
import logging
from pathlib import Path
from datetime import date, timedelta, datetime, timezone

# Setup — 强制绝对路径，防止相对路径导致数据写错位置
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

os.environ["DATABASE_URL"] = rf"sqlite:///{PROJECT_DIR}/quant/storage/quant.db"
os.environ["DATA_LAKE_DIR"] = str(PROJECT_DIR / "storage" / "lake")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_pipeline")

from apps.api.adapters.registry import default_adapter_registry
from apps.api.repositories.daily_bars import DailyBarRepository
from apps.api.repositories.stocks import StockRepository
from apps.api.repositories.trading_calendars import TradingCalendarRepository
from apps.api.db.session import get_engine, SessionLocal, init_db
from apps.api.models.entities import Stock, TradingCalendar

# ── 初始化 DB 表 ──
init_db()

def run_stock_list_sync():
    """全量股票列表同步"""
    logger.info("=" * 60)
    logger.info("📦 Step 1: 股票列表全量同步")
    logger.info("=" * 60)

    registry = default_adapter_registry()
    ak = registry.get("akshare")

    logger.info("  从 AKShare 拉取 A 股列表...")
    raw_records = ak.fetch_stock_list(market="A_SHARE")
    logger.info(f"  ✅ 获取到 {len(raw_records)} 只股票")

    # Normalize
    normalized = ak.normalize_stock_list(raw_records)
    logger.info(f"  ✅ 标准化后 {len(normalized)} 条")

    db = SessionLocal()
    try:
        repo = StockRepository(db)
        # Clear existing
        db.query(Stock).delete()
        db.flush()

        created = repo.upsert_many(normalized)
        db.commit()
        logger.info(f"  ✅ 写入 {created} 只股票到 SQLite")
    except Exception as e:
        db.rollback()
        logger.error(f"  ❌ 失败: {e}")
        raise
    finally:
        db.close()

    return len(normalized)


def run_daily_bars_sync(symbols: list[str], years: int = 3):
    """指定股票历史日K线同步"""
    logger.info("=" * 60)
    logger.info(f"📈 Step 2: 日K线历史同步 ({len(symbols)} 只, {years} 年)")
    logger.info("=" * 60)

    registry = default_adapter_registry()
    ak = registry.get("akshare")
    repo = DailyBarRepository()

    end_date = date.today()
    start_date = end_date - timedelta(days=years * 365)

    total_written = 0

    for symbol in symbols:
        logger.info(f"\n  🔄 {symbol} ({start_date} → {end_date})...")
        try:
            # Determine exchange
            if symbol.startswith("6"):
                exchange = "SSE"
            elif symbol.startswith("0") or symbol.startswith("3"):
                exchange = "SZSE"
            elif symbol.startswith("68"):
                exchange = "SSE"
            elif symbol.startswith("11") or symbol.startswith("13"):
                exchange = "BSE"
            else:
                exchange = "SSE"

            bars = ak.fetch_daily_bars(
                symbol=symbol,
                exchange=exchange,
                market="A_SHARE",
                start_date=start_date,
                end_date=end_date,
            )

            if not bars:
                logger.warning(f"  ⚠️ 无数据")
                continue

            # Normalize
            normalized = ak.normalize_daily_bars(bars)
            logger.info(f"  ✅ 标准化后 {len(normalized)} 条日K线")

            # Write to Parquet
            written = repo.write_many(normalized)
            logger.info(f"  ✅ 写入 {written} 条到 Parquet")
            total_written += written

        except Exception as e:
            logger.error(f"  ❌ {symbol} 失败: {e}")
            import traceback
            traceback.print_exc()

    logger.info(f"\n📊 总计写入 {total_written} 条日K线记录")
    return total_written


def run_calendar_sync():
    """交易日历同步"""
    logger.info("=" * 60)
    logger.info("📅 Step 3: 交易日历同步")
    logger.info("=" * 60)

    registry = default_adapter_registry()
    bs = registry.get("baostock")

    end_date = date.today() + timedelta(days=90)
    start_date = date.today() - timedelta(days=365)

    logger.info(f"  🔄 {start_date} → {end_date}...")
    records = bs.fetch_trading_calendar(market="A_SHARE", start_date=start_date, end_date=end_date)
    records = bs.normalize_trading_calendar(records, market="A_SHARE")
    logger.info(f"  ✅ 获取 {len(records)} 个交易日")

    db = SessionLocal()
    try:
        repo = TradingCalendarRepository(db)
        # Clear and reinsert
        db.query(TradingCalendar).delete()
        db.flush()

        created = repo.upsert_many(records)
        db.commit()
        logger.info(f"  ✅ 写入 {created} 条交易日历")
    except Exception as e:
        db.rollback()
        logger.error(f"  ❌ 失败: {e}")
        raise
    finally:
        db.close()

    return len(records)


def verify_data():
    """验证数据完整性"""
    logger.info("=" * 60)
    logger.info("🔍 数据验证")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        from sqlalchemy import func
        from apps.api.models.entities import Stock, TradingCalendar

        stock_count = db.query(func.count(Stock.id)).scalar()
        logger.info(f"  📦 SQLite stocks: {stock_count}")

        cal_count = db.query(func.count(TradingCalendar.id)).scalar()
        logger.info(f"  📅 SQLite trading_calendar: {cal_count}")

    finally:
        db.close()

    # Check Parquet
    repo = DailyBarRepository()
    try:
        total_bars = repo.count()
        logger.info(f"  📈 Parquet daily_bars: {total_bars}")

        latest = repo.latest_trade_date()
        logger.info(f"  📈 最新交易日: {latest}")
    except Exception as e:
        logger.warning(f"  ⚠️ Parquet 验证跳过: {e}")


if __name__ == "__main__":
    logger.info("🚀 Quant 数据管线初始化开始")
    logger.info(f"   Time: {datetime.now(timezone.utc).isoformat()}")

    # Step 1: Stock list
    stock_count = run_stock_list_sync()

    # Step 2: Daily bars for sample stocks
    sample_stocks = [
        "000001",   # 平安银行
        "000002",   # 万科A
        "600519",   # 贵州茅台
        "300750",   # 宁德时代
        "601318",   # 中国平安
        "000858",   # 五粮液
        "002594",   # 比亚迪
        "600036",   # 招商银行
        "601398",   # 工商银行
        "600276",   # 恒瑞医药
    ]
    bar_count = run_daily_bars_sync(sample_stocks, years=3)

    # Step 3: Trading calendar
    cal_count = run_calendar_sync()

    # Verify
    verify_data()

    logger.info("\n" + "=" * 60)
    logger.info("🎉 初始化完成！")
    logger.info(f"   股票: {stock_count} 只")
    logger.info(f"   日K线: {bar_count} 条")
    logger.info(f"   交易日: {cal_count} 天")
    logger.info("=" * 60)
