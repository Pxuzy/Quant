"""
Phase 3: 增量更新 A 股日K线数据（cron 友好）。

策略：
  1. 查 silver 最新交易日 → 从次日开始拉取
  2. 每批 500 只在独立子进程中运行（隔离 baostock GIL crash）
  3. 合并到新分区到 silver
"""
import sys
import os
import json
import time
import logging
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, ".")

from backend.app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("daily-update")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENV_PY = str(PROJECT_ROOT / "quant" / ".venv" / "Scripts" / "python.exe")
WORKER = Path(__file__).parent / "batch_fetch_worker.py"
RAW_DIR = PROJECT_ROOT / "storage" / "raw" / "daily_bars"
SILVER_DIR = Path(get_settings().data_lake_dir) / "silver" / "daily_bars"
BATCH_SIZE = 100


def get_last_trade_date() -> date | None:
    """查 silver 最新交易日"""
    import duckdb
    silver_path = (SILVER_DIR / "market=*" / "trade_date=*" / "*.parquet").resolve().as_posix()
    con = duckdb.connect()
    try:
        con.execute("SET threads TO 2;")
        result = con.execute(f"""
            SELECT max(trade_date) FROM read_parquet(
                glob('{silver_path}'), hive_partitioning=true
            )
        """).fetchone()[0]
        return result if isinstance(result, date) else date.fromisoformat(str(result)) if result else None
    except Exception:
        raw_files = list(RAW_DIR.glob("stock_*.parquet"))
        if raw_files:
            try:
                latest = con.execute(f"""
                    SELECT max(trade_date) FROM read_parquet(
                        '{RAW_DIR.resolve().as_posix()}/stock_*.parquet'
                    )
                """).fetchone()[0]
                return latest if isinstance(latest, date) else None
            except Exception:
                pass
        return None
    finally:
        con.close()


def incremental_merge_to_silver():
    """只把新数据合并到 silver"""
    import duckdb
    raw_files = sorted(RAW_DIR.glob("stock_*.parquet"))
    if not raw_files:
        log.warning("raw 目录没有数据")
        return

    silver_path = SILVER_DIR.resolve().as_posix()
    raw_glob = f"{RAW_DIR.resolve().as_posix()}/stock_*.parquet"

    con = duckdb.connect()
    try:
        con.execute("SET threads TO 4;")
        con.execute("SET memory_limit = '2GB';")

        try:
            last = con.execute(f"""
                SELECT max(trade_date) FROM read_parquet(
                    '{silver_path}/**/*.parquet', hive_partitioning=true
                )
            """).fetchone()[0]
        except Exception:
            last = None

        if last:
            log.info("silver latest: %s", last)
            new_count = con.execute(f"""
                SELECT count(*) FROM read_parquet('{raw_glob}')
                WHERE trade_date > '{last}'
            """).fetchone()[0]
            log.info("incremental: %d rows", new_count)
            if new_count == 0:
                log.info("no new data, skip merge")
                return

        con.execute(f"""
            COPY (
                SELECT DISTINCT ON (symbol, trade_date)
                    symbol, exchange, market, trade_date, "open", high, low, close,
                    pre_close, volume, amount, adjust_factor, adjust_type, source,
                    current_timestamp AS ingested_at
                FROM read_parquet('{raw_glob}')
                ORDER BY symbol, trade_date
            ) TO '{silver_path}'
            (FORMAT PARQUET, PARTITION_BY (market, trade_date), OVERWRITE_OR_IGNORE)
        """)

        total = con.execute(f"""
            SELECT count(*) FROM read_parquet(
                '{silver_path}/**/*.parquet', hive_partitioning=true
            )
        """).fetchone()[0]
        log.info("silver total: %d", total)

    finally:
        con.close()


def run_batch(symbols: list[str], start_date: str, end_date: str) -> tuple[int, int, int]:
    """Run a batch of symbols in a subprocess."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Write symbols to temp file
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(symbols, tmp)
    tmp.close()

    try:
        result = subprocess.run(
            [VENV_PY, str(WORKER), tmp.name, start_date, end_date, str(BATCH_SIZE)],
            capture_output=True, text=True, timeout=max(120, len(symbols) * 15),
            cwd=str(PROJECT_ROOT),
        )
        # Parse result from stdout
        for line in result.stdout.splitlines():
            if line.startswith("RESULT:"):
                parts = line.split(":")
                if len(parts) == 4:
                    return int(parts[1]), int(parts[2]), int(parts[3])

        log.warning("batch subprocess failed (exit %d): %s", result.returncode, result.stdout[-200:])
        return 0, len(symbols), 0
    finally:
        os.unlink(tmp.name)


def main():
    t0 = time.time()
    log.info("=" * 50)
    log.info("Phase 3: A-share daily bar incremental update")

    today = date.today()
    last_date = get_last_trade_date()

    if last_date and last_date >= today:
        log.info("data up to date (%s), skip", last_date)
        return

    start_from = (last_date + timedelta(days=1)) if last_date else date(2022, 7, 1)
    log.info("latest: %s, fetch from %s", last_date or "none", start_from)

    # 1. Get stock list
    from backend.app.db.session import get_engine, SessionLocal
    from backend.app.repositories.stocks import StockRepository
    engine = get_engine()
    SessionLocal.configure(bind=engine)
    db = SessionLocal()
    stocks = StockRepository(db).list_market_stocks(
        market="A_SHARE", status="LISTED", common_only=True
    )
    db.close()
    symbols = []
    seen = set()
    for s in stocks:
        if s.symbol not in seen:
            seen.add(s.symbol)
            symbols.append(s.symbol)
    log.info("A-share: %d stocks", len(symbols))

    # 2. Process in batches via subprocess
    total_success = total_failed = total_bars = 0
    batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches, 1):
        log.info("batch %d/%d (%d stocks)...", batch_idx, len(batches), len(batch))
        success, failed, bars = run_batch(batch, start_from.isoformat(), today.isoformat())
        total_success += success
        total_failed += failed
        total_bars += bars
        log.info("  batch %d done: OK %d FAIL %d +%d bars", batch_idx, success, failed, bars)

    log.info("fetch done: OK %d FAIL %d +%d bars", total_success, total_failed, total_bars)
    log.info("merging to silver...")
    incremental_merge_to_silver()

    elapsed = time.time() - t0
    log.info("done in %.1fs", elapsed)


if __name__ == "__main__":
    main()
