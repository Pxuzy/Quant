"""
Phase 2: 将 raw/ 数据合并到 silver/ 分区表。

策略（吸收 Qlib dump_bin 思想）：
  1. DuckDB 一次性读取 raw/*.parquet
  2. SQL 全局去重 (DISTINCT ON symbol, trade_date)
  3. COPY TO silver/ WITH PARTITION_BY 一行搞定分区写入
  4. 纯本地计算，可用多线程并行读

用法：
  quant/.venv/Scripts/python.exe scripts/ops/merge_raw_to_silver.py
  quant/.venv/Scripts/python.exe scripts/ops/merge_raw_to_silver.py --dry-run

输入：storage/raw/daily_bars/{symbol}.parquet
输出：storage/lake/silver/daily_bars/market=X/trade_date=Y/part-000.parquet
"""
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

from apps.api.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("merge")

RAW_DIR = Path("storage/raw/daily_bars")
SILVER_DIR = Path(get_settings().data_lake_dir) / "silver" / "daily_bars"


def merge_to_silver(dry_run: bool = False, cleanup: bool = False, batch_size: int = 500):
    """读取 raw/ 全部 parquet，去重后写入 silver/ 分区表"""
    import duckdb

    raw_files = sorted(RAW_DIR.glob("stock_*.parquet"))
    if not raw_files:
        log.warning("raw 目录没有数据文件: %s", RAW_DIR.resolve())
        return

    log.info("=" * 50)
    log.info("Phase 2: raw → silver 合并")
    log.info("  raw 文件: %d 个", len(raw_files))
    log.info("  silver 目标: %s", SILVER_DIR.resolve())

    t0 = time.time()

    con = duckdb.connect()
    try:
        # 1. 启用并行（利用多核）
        con.execute("SET threads TO 4;")
        con.execute("SET memory_limit = '2GB';")

        # 2. 注册 raw 文件列表
        raw_glob = f"'{RAW_DIR.resolve().as_posix()}/stock_*.parquet'"
        con.execute(f"""
            CREATE TABLE raw_bars AS
            SELECT * FROM read_parquet({raw_glob})
        """)

        row_count = con.execute("SELECT count(*) FROM raw_bars").fetchone()[0]
        symbol_count = con.execute("SELECT count(DISTINCT symbol) FROM raw_bars").fetchone()[0]
        log.info("  原始数据: %d 条, %d 只股票", row_count, symbol_count)

        if row_count == 0:
            log.warning("没有数据可合并")
            return

        # 3. 全局去重（保留最后一条 ingested）
        con.execute(f"""
            CREATE TABLE deduped AS
            SELECT DISTINCT ON (symbol, trade_date)
                symbol,
                exchange,
                market,
                trade_date,
                "open",
                high,
                low,
                close,
                pre_close,
                volume,
                amount,
                adjust_factor,
                adjust_type,
                source,
                current_timestamp AS ingested_at
            FROM raw_bars
            ORDER BY symbol, trade_date
        """)

        dedup_count = con.execute("SELECT count(*) FROM deduped").fetchone()[0]
        dupes = row_count - dedup_count
        if dupes > 0:
            log.info("  去重: 移除 %d 条重复", dupes)
        log.info("  去重后: %d 条", dedup_count)

        if dry_run:
            log.info("  [DRY RUN] 跳过写入 silver")
            # 展示统计
            stats = con.execute("""
                SELECT market, count(*) as bars, count(DISTINCT symbol) as stocks,
                       min(trade_date) as first, max(trade_date) as last
                FROM deduped GROUP BY market ORDER BY market
            """).fetchall()
            for row in stats:
                log.info("    %s: %d 条, %d 只, %s ~ %s", *row)
            return

        # 4. 写入分区表（先清理目标目录防止同名残留）
        import pyarrow as pa
        import pyarrow.parquet as pq
        import shutil

        for market_dir in SILVER_DIR.glob("market=*"):
            market_dir_path = Path(market_dir)
            for date_dir in market_dir_path.glob("trade_date=*"):
                shutil.rmtree(date_dir)
                date_dir.mkdir(parents=True, exist_ok=True)

        deduped_table = con.execute("SELECT * FROM deduped ORDER BY trade_date").to_arrow_table()
        pq.write_to_dataset(
            deduped_table,
            root_path=str(SILVER_DIR),
            partition_cols=["market", "trade_date"],
            existing_data_behavior="delete_matching",
            basename_template="part-{i}.parquet",
        )

        # 5. 统计写入结果
        elapsed = time.time() - t0
        silver_str = SILVER_DIR.resolve().as_posix()
        written = con.execute(f"""
            SELECT count(*) FROM read_parquet(
                '{silver_str}/market=*/trade_date=*/part-*.parquet', hive_partitioning=true
            )
        """).fetchone()[0]

        partitions = con.execute(f"""
            SELECT count(DISTINCT trade_date) FROM read_parquet(
                '{silver_str}/market=*/trade_date=*/part-*.parquet', hive_partitioning=true
            )
        """).fetchone()[0]

        log.info("✅ 合并完成!")
        log.info("  silver 条数: %d", written)
        log.info("  分区数: %d", partitions)
        log.info("  耗时: %.1f 秒", elapsed)
        log.info("  目录: %s", silver_str)

        # 7. 同步更新 Stock 表的 latest_data_date 和 data_completeness
        _sync_stock_data_coverage(con)

        # 8. 清理 raw/ 数据（可选）
        log.info("")
        log.info("💡 raw/ 数据可保留用于下次增量合并, 也可删除释放空间")
        raw_size = sum(f.stat().st_size for f in raw_files)
        log.info("  raw 占用: %.1f MB (%d 文件)", raw_size / 1024 / 1024, len(raw_files))

        # 7. 清理 raw/ 数据（可选）
        if cleanup:
            import shutil
            shutil.rmtree(RAW_DIR)
            log.info("  已清理 raw/ 数据，释放 %.1f MB", raw_size / 1024 / 1024)

    except Exception as e:
        log.error("合并失败: %s", e)
        raise
    finally:
        con.close()


def _sync_stock_data_coverage(con):
    """Sync latest_data_date and data_completeness from silver Parquet to Stock table."""
    import logging
    log = logging.getLogger("merge")

    # Query silver for per-symbol stats
    raw_glob = f"{RAW_DIR.resolve().as_posix()}/stock_*.parquet"
    rows = con.execute(f"""
        SELECT symbol, min(trade_date) as first_date, max(trade_date) as latest_date,
               count(distinct trade_date) as trade_days
        FROM read_parquet('{raw_glob}')
        GROUP BY symbol
    """).fetchall()

    if not rows:
        return

    log.info(f"  Syncing {len(rows)} stocks to DB...")

    # Use SQLAlchemy engine to update Stock table (DuckDB can't see SQLite tables)
    from apps.api.db.session import get_engine
    from sqlalchemy import text
    from datetime import datetime, timezone

    engine = get_engine()
    now = datetime.now(timezone.utc)
    with engine.connect() as conn:
        for row in rows:
            symbol = row[0]
            latest_date = row[2]
            trade_days = row[3]
            completeness = round(min(1.0, trade_days / 965.0), 4) if trade_days else None
            conn.execute(
                text("UPDATE stocks SET latest_data_date = :d, data_completeness = :c, updated_at = :u WHERE symbol = :s"),
                {"d": latest_date, "c": completeness, "u": now, "s": symbol}
            )
        conn.commit()

    log.info(f"  Synced {len(rows)} stocks")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase 2: Merge raw bars to silver")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    parser.add_argument("--cleanup", action="store_true", help="合并后清理 raw/ 数据")
    args = parser.parse_args()
    merge_to_silver(dry_run=args.dry_run, cleanup=args.cleanup)
